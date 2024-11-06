import os
import shutil
import datetime

def archive_speech():
    source_folder = "speech_folder"
    # Create the main archive folder if it doesn't exist
    archive_folder = os.path.join(source_folder, 'archive')
    os.makedirs(archive_folder, exist_ok=True)

    # Create a timestamped subfolder
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    timestamped_folder = os.path.join(archive_folder, timestamp)
    os.makedirs(timestamped_folder, exist_ok=True)

    # Counter for moved files
    moved_files = 0

    # Iterate through all files in the source folder
    for filename in os.listdir(source_folder):
        if filename.lower().endswith('.mp3'):
            source_file = os.path.join(source_folder, filename)
            destination_file = os.path.join(timestamped_folder, filename)
            
            # Move the file
            shutil.move(source_file, destination_file)
            moved_files += 1
            print(f"Moved: {filename}")

    print(f"\nTotal files moved: {moved_files}")
    print(f"Files moved to: {timestamped_folder}")
