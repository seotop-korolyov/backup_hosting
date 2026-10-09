#!/usr/bin/python3

# Modules
import json, os, sys, subprocess
from datetime import datetime
from ftplib import FTP

# Restrict permissions of newly created files
os.umask(0o077)

# Global variables
config_file_bd = "config.json"

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
    #Fix is the file wasn't found, may be the config is not right
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
def backup_database(credentials):
  data = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
  backup_file = f"{data}_{credentials['dbase']}.sql.gz"
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

  return success

# Connect to BackUp server via FTP
def ftp_connection(ftp_credentials):
  data = datetime.now().strftime("%Y-%m-%d")
  host = ftp_credentials["host"]
  port = ftp_credentials["port"]
  username = ftp_credentials["username"]
  password = os.environ.get("BACKUP_FTP_PASSWORD")
  remote_directory = ftp_credentials["remote_directory"]

  new_dir = f"{remote_directory}/{data}"

  ftp = FTP()
  ftp.connect(host, port, timeout=15)
  ftp.login(username, password)
  ftp.mkd(new_dir)
  ftp.dir(remote_directory)

# Get configs from conf.json
configs = get_config(config_file_bd)

#Get db credentials
results = {}
for db_config in configs["databases"]:
  db_credentials = get_db_credentials(db_config["credentials_file"])

  #Backup db
  #success = backup_database(db_credentials)
  #results[db_credentials["dbase"]] = success

# Get FTP credentials
ftp_credentials = get_ftp_config(configs["ftp"])

# Connect to BackUp server
ftp_connection(ftp_credentials)

#OutPut for tests
print("========== DATABASE BACKUP REPORT ==========")

for db, status in results.items():
  if status:
    print(f"{db}: SUCCESS")
  else:
    print(f"{db}: FAILED")

print(f"\nTotal databases: {len(results)}")

successful = sum(results.values())
failed = len(results) - successful
print(f"Successful: {successful}")
print(f"Failed: {failed}")

if results and all(results.values()):
  print("Overall status: SUCCESS")
  sys.exit(0)
else:
  print("Overall status: FAILED")
  sys.exit(1)