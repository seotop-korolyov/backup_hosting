#!/usr/bin/python3

# Modules
import json, os, sys, subprocess, gzip, zlib, hashlib
from datetime import datetime
from ftplib import FTP, all_errors, error_perm

# Restrict permissions of newly created files
os.umask(0o077)

# Global variables
config_file_bd = "config.json"
db_backup_dir = "db"
files_backup_dir = "websites"
data = datetime.now().strftime("%Y-%m-%d")

# Check if the config exist
if not os.path.exists(config_file_bd):
  print(f"File {config_file_bd} does not exist")
  sys.exit(1)

# Get databases from config.json
def get_config(config_file_bd):
  try:
    with open(config_file_bd, "r") as file:
      config = json.load(file)
    return config
  except json.JSONDecodeError:
    print(f"The {config_file_bd} is not correct")
    sys.exit(1)
  except FileNotFoundError:
    print(f"The file {config_file_bd} is not found")
    sys.exit(1)

# get db credentials
def get_db_credentials(credentials_file):
  wanted = (
    "database_server",
    "database_user",
    "database_password",
    "dbase"
  )
  credentials = {}
  try:
    with open(credentials_file, "r") as file:
      for line in file:
        if "=" not in line:
          continue

        part = line.split("=", 1)

        variable = part[0].strip().strip("$")
        if variable in wanted:
          value = part[1].strip().strip("'';")
          if len(value) == 0:
            continue
          credentials[variable] = value

      #Checking whether we got all credentials
      missing = set(wanted) - set(credentials)
      if missing:
        print(f"There are a missing credentials {missing}")
        sys.exit(1)

      return credentials
  except FileNotFoundError:
    print(f"The file {credentials_file} is not found")
    sys.exit(1)

# get ftp credentials
def get_ftp_config(configs):
  credentials = {
    "host": configs["host"],
    "port": configs["port"],
    "username": configs["username"],
    "remote_directory": configs["remote_directory"]
  }

  return credentials

#Backup database
def backup_database(credentials, backup_file):
  env = os.environ.copy()
  env["MYSQL_PWD"] = credentials["database_password"]
  command = [
    "mysqldump",
    "-h", credentials["database_server"],
    "-u", credentials["database_user"],
    "--no-tablespaces",
    credentials["dbase"]
  ]
  dump_process = None
  gzip_process = None
  dump_returncode = None
  gzip_returncode = None
  success = False
  file_created = False
  
  try:
    with open(backup_file, "xb") as file:
      file_created = True
      dump_process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        env=env
      )
      try:
        gzip_process = subprocess.Popen(
        ["gzip"],
        stdin=dump_process.stdout,
        stdout=file
        )
      finally:
        dump_process.stdout.close()

      gzip_returncode = gzip_process.wait()
      dump_returncode = dump_process.wait()

      if dump_returncode == 0 and gzip_returncode == 0:
        success = True
      else:
        print(
          f"Backup failed: {credentials['dbase']}, "
          f"mysqldump={dump_returncode}, "
          f"gzip={gzip_returncode}"
        )
  except OSError as error:
    print(f"Backup error: {error}")
  finally:
    #Stop and reap processes if an exception interrupted the pipeline
    for process in (gzip_process, dump_process):
      if process is not None and process.poll() is None:
        process.terminate()
        try:
          process.wait(timeout=5)
        except subprocess.TimeoutExpired:
          process.kill()
          process.wait()
  
    # Delete incomplete archives after the file has closed
    if file_created and not success:
      try:
        os.remove(backup_file)
      except FileNotFoundError:
        pass
      except OSError as error:
        print(f"Could not remove incomplete archive: {error}")

  return success, dump_returncode, gzip_returncode

# Connect to BackUp server via FTP
def ftp_connection(ftp_credentials):
  host = ftp_credentials["host"]
  port = ftp_credentials["port"]
  username = ftp_credentials["username"]
  password = os.environ.get("BACKUP_FTP_PASSWORD")
  remote_directory = ftp_credentials["remote_directory"]

  if not password:
    print("FTP password is not configured")
    return None

  ftp = FTP()
  try:
    ftp.connect(host, port, timeout=15)
    ftp.login(username, password)
    
    try:
      ftp.cwd(remote_directory)
    except error_perm as error:
      print(f"Cannot access backup directory: {error}")
      ftp.close()    
      return None
    
    return ftp
  except all_errors as error:
    print(f"FTP error: {error}")
    ftp.close()
    return None

# Upload backup
def upload_backup(ftp, backup_file):
  remote_filename = os.path.basename(backup_file)
  temporary_filename = remote_filename + ".part"

  try:
    with open(backup_file, "rb") as file:
      ftp.storbinary(
        f"STOR {temporary_filename}", 
        file
      )

    local_file_size = os.path.getsize(backup_file)
    remote_file_size = ftp.size(os.path.basename(temporary_filename))
      
    if local_file_size == remote_file_size:
      ftp.rename(temporary_filename, remote_filename)
      return True
    else:
      return False
  except all_errors as error:
    print(f"FTP upload failed: {error}")
    return False

# Ensure ftp directory
def ensure_ftp_directory(ftp, directory):
  try:
    ftp.cwd(directory)
  except error_perm:
    ftp.mkd(directory)
    ftp.cwd(directory)
  cwd_path = ftp.pwd()

  return cwd_path

# Check remote backup file
def check_remote_backup(ftp, backup_file):
  try:
    files = ftp.nlst()
  except all_errors as error:
    print(f"Cannot list remote file {error}")
    return None

  remote_names = [
    os.path.basename(name.rstrip("/"))
    for name in files
  ]
  if backup_file in remote_names:
    print(f"Remote file {backup_file} exist")
    return True
  return False

# Check local file backup
def check_local_backup(backup_file):
  if not os.path.isfile(backup_file):
    l_file_status = "MISSING"
    return l_file_status

  try:
    if os.path.getsize(backup_file) == 0:
      l_file_status = "INVALID"
      return l_file_status
    
    with gzip.open(backup_file, "rb") as file:
      while file.read(1024 * 1024):
        pass
    l_file_status = "VALID_GZIP"
    return l_file_status
  except (OSError, EOFError, zlib.error) as error:
    print(f"Invalid local backup {backup_file}: {error}")
    l_file_status = "INVALID"
    return l_file_status

# Delete a local bakup file
def delete_local_backup(backup_file):
  try:
    os.remove(backup_file)
    print(f"Local archive deleted: {backup_file}")
    return True
  except OSError as error:
    print(f"Remove {backup_file}: {error}")
    return False

# Save backup metadata
def save_backup_metadata(
    backup_file,
    db_name,
    dump_returncode,
    gzip_returncode,
    data
):
  try:
    l_file_size = os.path.getsize(backup_file)
  except (OSError, TypeError, ValueError) as error:
    print(f"File size is failed: {error}")
    return False

  # Calculate SHA256
  checksum = calculate_sha256(backup_file)
  if checksum is None:
    print(f"Cannot calculate checksum: {backup_file}")
    return False

  results = {
    "database": db_name,
    "backup_file": backup_file,
    "date": data,
    "dump_exit_code": dump_returncode,
    "gzip_exit_code": gzip_returncode,
    "size": l_file_size,
    "sha256": checksum,
    "status": "COMPLETE"
  }
  metadata_file = backup_file + ".json"
  temporary_file = metadata_file + ".tmp"

  try:
    with open(temporary_file, "w") as file:
      json.dump(results, file, indent=2)
      file.flush()
      os.fsync(file.fileno())
    os.replace(temporary_file, metadata_file)
    return True
  except (OSError, TypeError, ValueError) as error:
    print(f"The {backup_file}.json was not creeated: {error}")
    return False

# Check backup metadata
def check_backup_metadata(backup_file, db_name):
  metadata_file = backup_file + ".json"
  
  try:
    l_file_size = os.path.getsize(backup_file)
    current_checksum = calculate_sha256(backup_file)
    
    if current_checksum is None:
      return False

    with open(metadata_file, "r") as file:
      metadata = json.load(file)

    if not isinstance(metadata, dict):
      return False
      
    if metadata["database"] != db_name:
      return False
    elif metadata["dump_exit_code"] != 0:
      return False
    elif metadata["gzip_exit_code"] != 0:
      return False
    elif metadata["size"] != l_file_size:
      return False
    elif metadata["status"] != "COMPLETE":
      return False
    elif metadata["backup_file"] != backup_file:
      return False
    elif metadata["sha256"] != current_checksum:
      print(f"SHA-256 mismatch: {backup_file}")
      return False
    return True
  
  except json.JSONDecodeError:
    print(f"The {metadata_file} is not correct")
    return False
  
  except (OSError, TypeError, ValueError, KeyError) as error:
    print(f"Open {metadata_file}: {error}")
    return False

# Calculate SHA256
def calculate_sha256(backup_file):
  sha256 = hashlib.sha256()
  try:
    with open(backup_file, "rb") as file:
      while True:
        chunk = file.read(1024 * 1024)

        if not chunk:
          break

        sha256.update(chunk)
    return sha256.hexdigest()
  except OSError as error:
    print(f"SHA-256 calculation failed: {error}")
    return None


# Get configs from conf.json
configs = get_config(config_file_bd)

# Get FTP credentials
ftp_credentials = get_ftp_config(configs["ftp"])

# Connect to BackUp server
ftp = ftp_connection(ftp_credentials)

if ftp is None:
  print("FTP connection failed")
  sys.exit(1)

# Change directory
if ftp is not None:
  try:
    ensure_ftp_directory(ftp, db_backup_dir)
    current_dir = ensure_ftp_directory(ftp, data)

  except all_errors as error:
    print(f"FTP directory error: {error}")
    ftp.close()
    ftp = None
else:
  print("FTP connection failed")

#Get db credentials
results = {}
for db_config in configs["databases"]:
  db_credentials = get_db_credentials(db_config["credentials_file"])
  db_name = db_credentials["dbase"]
  results[db_name] = "FAILED"

  backup_file = f"{data}_{db_name}.sql.gz"

  # Check whether remote file exist
  if ftp is not None:
    remote_exists = check_remote_backup(ftp, backup_file)
    if remote_exists is None:
      results[db_name] = "FAILED"
      continue

    if remote_exists:
      results[db_name] = "ALREADY_EXISTS"
      continue

  # Check local file backup
  l_file_status = check_local_backup(backup_file)
  if l_file_status == "VALID_GZIP":
    if check_backup_metadata(backup_file, db_name):
      print(f"Verified local backup: {backup_file}")
      success = True
    else: 
      print(f"Backup metadata invalid: {backup_file}")
      results[db_name] = "FAILED"
      continue
  elif l_file_status == "MISSING":
    # Backup db
    success, \
    dump_returncode, \
    gzip_returncode = backup_database(db_credentials, backup_file)

    if not success:
      print(f"Database backup failed: {db_name}")
      continue
    
    metadata_success = save_backup_metadata(
      backup_file, 
      db_name, 
      dump_returncode, 
      gzip_returncode,
      data
    )
    if not metadata_success:
      print(f"Metadata creation failed: {db_name}")
      continue
    
  elif l_file_status == "INVALID":
    print(f"Invalid local archive: {backup_file}")
    results[db_name] = "FAILED"
    continue

  # Upload
  if success and ftp is not None:
    upload_success = upload_backup(ftp, backup_file)
    if upload_success:
      # Temporary commited
      #delete_local_backup(backup_file)
      results[db_name] = "SUCCESS"
  else:
    print("FTP connection failed")

# Close FTP connection
if ftp is not None:
  try:
    ftp.quit()
  except all_errors:
    ftp.close()

#OutPut for tests
print("========== DATABASE BACKUP REPORT ==========")

for db, status in results.items():
  print(f"Backup: {db} [ {status} ]")

print(f"\nTotal databases: {len(results)}")

successful = sum(
  status == "SUCCESS"
  for status in results.values()
)
existing = sum(
    status == "ALREADY_EXISTS"
    for status in results.values()
)
count_db = len(results)
failed = count_db - (successful + existing)

print(f"Successful: {successful}")
print(f"Already exist: {existing}")
print(f"Failed: {failed}")

if successful + existing == count_db:
  print("Overall status: SUCCESS")
  sys.exit(0)
else:
  print("Overall status: FAILED")
  sys.exit(1)