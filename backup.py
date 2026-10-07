#!/usr/bin/python3

#Modules
import json, os, sys, subprocess
from datetime import datetime

#Clear the screen
subprocess.run(["clear"])

#Global variables
config_file_bd = "config.json"

#Check if the config exist
if not os.path.exists(config_file_bd):
  print(f"File {config_file_bd} does not exist")
  sys.exit(1)

#Get databases from config.json
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

#get db credentials
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

#Backup database
def backup_database(credentials):
  data = datetime.now().strftime("%Y-%m-%d")
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

  with open(backup_file, "wb") as file:
    dump_process = subprocess.Popen(
      command,
      stdout=subprocess.PIPE,
      env=env
    )

    gzip_process = subprocess.Popen(
      ["gzip"],
      stdin=dump_process.stdout,
      stdout=file
    )
    dump_process.stdout.close()
    gzip_returncode = gzip_process.wait()
    dump_returncode = dump_process.wait()
    print(dump_returncode)
    print(gzip_returncode)

configs = get_config(config_file_bd)

#Get db credentials

for config in configs["databases"]:
  credentials = get_db_credentials(config["credentials_file"])

  #Backup db
  backup_database(credentials)
    