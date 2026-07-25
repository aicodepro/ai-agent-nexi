import speech_recognition as sr
import eel
import os
import requests
from typing import Union
from os import getcwd

def is_online(url="https://www.google.com", timeout=5):
    try:
        response = requests.get(url, timeout=timeout)
        return response.status_code >= 200 and response.status_code < 300
    except requests.ConnectionError:
        return False
    except requests.Timeout:
        return False
    except Exception as e:
        print(f"Error in is_online function: {e}")
        return False

def generate_audio(message: str, voice: str = "Aditi"):
    url = f"https://api.streamelements.com/kappa/v2/speech?voice={voice}&text={message}"
    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'}
    try:
        result = requests.get(url=url, headers=headers)
        return result.content
    except Exception as e:
        print(f"Error generating audio: {e}")
        return None

def speak_streamelements(message: str, voice: str = "Aditi", folder: str = "", extension: str = ".mp3") -> Union[None, str]:
    try:
        from engine.command import speak as authoritative_speak
        authoritative_speak(str(message), voice=voice)
        return None
    except Exception as e:
        print(f"Error in speak_streamelements: {e}")
        return str(e)

def speak_pyttsx3(text):
    try:
        from engine.command import speak as authoritative_speak
        authoritative_speak(str(text))
    except Exception as e:
        print(f"Error in speak_pyttsx3 function: {e}")

def speak(text, voice="Matthew"):
    from engine.command import speak as authoritative_speak
    authoritative_speak(str(text), voice=voice)
import os

import os
from pathlib import Path

def create_folder_and_files(query):
    try:
        # Parse the command for the folder name, directory, and files
        if "create a folder named" in query and "in" in query and "and add" in query:
            folder_name = query.split("create a folder named ")[-1].split(" in ")[0].strip()
            directory_part = query.split(" in ")[-1].split(" and add ")[0].strip()
            file_list = query.split("and add ")[-1].strip().split(" ")

            # Map common directories to their paths or get exact paths
            directories = {
                "desktop": str(Path.home() / "Desktop"),
                "documents": str(Path.home() / "Documents"),
                "downloads": str(Path.home() / "Downloads"),
                "pictures": str(Path.home() / "Pictures"),
                "music": str(Path.home() / "Music"),
                "videos": str(Path.home() / "Videos"),
            }
            directory_path = directories.get(directory_part.lower(), directory_part)

            # Ensure the directory exists
            if not os.path.exists(directory_path):
                speak(f"The specified directory does not exist: {directory_part}")
                return

            # Create the folder in the specified directory
            folder_path = os.path.join(directory_path, folder_name)
            os.makedirs(folder_path, exist_ok=True)
            print(f"Folder '{folder_name}' created in {directory_part}.")

            # Create the files inside the folder
            for file_name in file_list:
                file_name = file_name.strip()
                file_path = os.path.join(folder_path, file_name)

                # Choose content based on file extension
                if file_name.endswith(".html"):
                    content = "<!DOCTYPE html>\n<html>\n<head>\n    <title>Document</title>\n</head>\n<body>\n</body>\n</html>"
                elif file_name.endswith(".py"):
                    content = f"# {file_name}\n\nif __name__ == '__main__':\n    print('Hello, World!')"
                elif file_name.endswith(".js"):
                    content = "console.log('Hello, World!');"
                elif file_name.endswith(".css"):
                    content = "body {\n    font-family: Arial, sans-serif;\n}"
                else:
                    content = ""

                # Create and write to the file
                with open(file_path, 'w') as f:
                    f.write(content)
                print(f"File '{file_name}' created in folder '{folder_name}'.")

            speak("The folder and files have been created successfully.")

        else:
            speak("I did not understand the command. Please try again.")

    except Exception as e:
        print(f"Error in create_folder_and_files: {e}")
        speak(f"An error occurred: {e}")


def create_file_in_existing_folder(query):
    try:
        # Parse the command for the folder location, folder name, and file name
        if "create a new file in" in query and "and name it as" in query:
            location_part = query.split("create a new file in ")[-1].split(" and name it as ")[0].strip()
            file_name = query.split("and name it as ")[-1].strip()

            # Separate the folder name and its location
            if " in " in location_part:
                folder_name = location_part.split(" in ")[0].strip()
                location_directory = location_part.split(" in ")[-1].strip()
            else:
                folder_name = location_part
                location_directory = ""

            # Map common directories to their paths or get exact paths
            directories = {
                "desktop": str(Path.home() / "Desktop"),
                "documents": str(Path.home() / "Documents"),
                "downloads": str(Path.home() / "Downloads"),
                "pictures": str(Path.home() / "Pictures"),
                "music": str(Path.home() / "Music"),
                "videos": str(Path.home() / "Videos"),
            }
            base_path = directories.get(location_directory.lower(), location_directory)

            # Combine base path with the folder name
            folder_path = os.path.join(base_path, folder_name)

            # Check if the folder exists
            if not os.path.exists(folder_path):
                speak(f"The specified folder '{folder_name}' does not exist in {base_path}.")
                return

            # Create the file inside the specified folder
            file_path = os.path.join(folder_path, file_name)
            
            # Determine content based on file extension
            if file_name.endswith(".json"):
                content = "{}"  # Empty JSON object
            elif file_name.endswith(".txt"):
                content = "This is a new text file."
            elif file_name.endswith(".bash"):
                content = "#!/bin/bash\n# Bash script"
            elif file_name.endswith(".db"):
                content = ""  # For .db files, we'll just create an empty file
            else:
                content = ""

            # Create and write to the file
            with open(file_path, 'w') as f:
                f.write(content)
            print(f"File '{file_name}' created in folder '{folder_name}'.")

            speak(f"The file '{file_name}' has been created successfully in the '{folder_name}' folder in {location_directory}.")

        else:
            speak("I did not understand the command. Please try again.")

    except Exception as e:
        print(f"Error in create_file_in_existing_folder: {e}")
        speak(f"An error occurred: {e}")
