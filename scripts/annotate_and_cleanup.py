from dotenv import load_dotenv
load_dotenv(dotenv_path="backend/.env")
import os
from openai import OpenAI
from utils import get_project_root

# Set your OpenAI API key
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Supported extensions
TARGET_EXTENSIONS = [".py", ".ts", ".tsx", ".jsx"]

# Target directories
PROJECT_ROOT = get_project_root()
# BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")
FRONTEND_DIR = os.path.join(PROJECT_ROOT, "frontend")


def collect_files(base_dir):
    code_files = []
    ignored_dirs = {"node_modules", ".next", "build", "dist", ".git", "public", "__pycache__", "venv", ".venv", ".env"}

    for root, dirs, files in os.walk(base_dir):
        # Modify dirs in-place to skip ignored directories
        dirs[:] = [d for d in dirs if d not in ignored_dirs]

        for file in files:
            if any(file.endswith(ext) for ext in TARGET_EXTENSIONS):
                full_path = os.path.join(root, file)
                code_files.append(full_path)
    return code_files


def annotate_code(file_content, filename):
    prompt = (
        f"Add only in-line comments and basic logging statements to this code file.\n"
        f"- Do NOT delete or simplify any code.\n"
        f"- Do NOT insert summary paragraphs or high-level overviews.\n"
        f"- Do NOT alter function names or logic.\n"
        f"- Use consistent indentation and formatting.\n\n"
        f"Filename: {filename}\n\n"
        f"{file_content}"
    )
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are a careful assistant who adds helpful code comments without changing logic."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2,
    )
    return response.choices[0].message.content


def process_file(filepath):
    with open(filepath, "r") as f:
        content = f.read()

    print(f"Processing: {filepath}")
    annotated = annotate_code(content, filepath)

    with open(filepath, "w") as f:
        f.write(annotated)


def main():
    # backend_files = collect_files(BACKEND_DIR)
    frontend_files = collect_files(FRONTEND_DIR)
    # all_files = backend_files + frontend_files
    all_files = frontend_files

    for filepath in all_files:
        try:
            process_file(filepath)
        except Exception as e:
            print(f"Error processing {filepath}: {e}")


if __name__ == "__main__":
    main()
