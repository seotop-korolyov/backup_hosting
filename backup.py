#!/usr/bin/python3

#Modules
import json, os, sys, subprocess

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
    print(f"The file {config_file_bd} is not found")
    sys.exit(1)

#get db credentials
def get_db_credentials(credentials_file):
  try:
    with open(credentials_file, "r") as file:
      for line in file:
        print(line)
  except FileNotFoundError:
    print(f"The file {credentials_file} is not found")
    sys.exit(1)

configs = get_config(config_file_bd)

for config in configs["databases"]:
  get_db_credentials(config["credentials_file"])

    