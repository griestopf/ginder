import os

path_to_secrets = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ginder_secrets.py')
print(path_to_secrets)
f = open(path_to_secrets, "a")
f.write(f"ginder_token = 'Dödeldödeljü'\n")
f.close()

