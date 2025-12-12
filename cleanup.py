import os
import shutil
import pathlib

def clean_project():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    print(f"🧹 Cleaning project at: {root_dir}")
    
    deleted_files = 0
    deleted_folders = 0

    for current_dir, dirs, files in os.walk(root_dir):
        # 1. Delete __pycache__ folders
        if "__pycache__" in dirs:
            cache_path = os.path.join(current_dir, "__pycache__")
            try:
                shutil.rmtree(cache_path)
                print(f"   Deleted folder: {cache_path}")
                deleted_folders += 1
            except Exception as e:
                print(f"   ❌ Error deleting {cache_path}: {e}")
            dirs.remove("__pycache__") # Don't traverse into it

        # 2. Delete .pyc files (just in case they are loose)
        for file in files:
            if file.endswith(".pyc") or file.endswith(".pyo"):
                file_path = os.path.join(current_dir, file)
                try:
                    os.remove(file_path)
                    deleted_files += 1
                except Exception as e:
                    print(f"   ❌ Error deleting {file_path}: {e}")

    print("-" * 30)
    print(f"✨ Cleanup Complete!")
    print(f"   Removed {deleted_folders} __pycache__ folders")
    print(f"   Removed {deleted_files} .pyc files")
    print("-" * 30)

if __name__ == "__main__":
    clean_project()