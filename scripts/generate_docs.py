from dotenv import load_dotenv
from utils import get_project_root
load_dotenv(dotenv_path="backend/.env")
import os
from openai import OpenAI

# Load your OpenAI API key from environment variable
client = OpenAI()

PROJECT_ROOT = get_project_root()
PROJECT_DIRS = ["frontend", "backend"]
OUTPUT_DOC_PATH = "docs/index.md"

# Walk through frontend and backend for .ts, .tsx, and .py files
def read_project_files(directories):
    source_files = []
    for root_dir in directories:
        for root, dirs, files in os.walk(root_dir):
            if any(skip in root for skip in ("node_modules", "venv", ".venv", "__pycache__")):
                continue
            for file in files:
                if file.endswith((".ts", ".tsx", ".py")):
                    full_path = os.path.join(root, file)
                    with open(full_path, "r") as f:
                        content = f.read()
                        relative_path = os.path.relpath(full_path)
                        source_files.append((relative_path, content))
    return source_files

def generate_doc(content, filename):
    prompt = f"""You're a technical writer helping document TypeScript interfaces.
The following is a file named `{filename}` containing TypeScript types. Generate Markdown documentation from it:
```
{content}
```"""
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    )
    return response.choices[0].message.content.strip()

def main():
    print("📄 Reading project files...")
    source_files = read_project_files(PROJECT_DIRS)

    all_docs = """
---
layout: default
title: Manifest Documentation
permalink: /docs/
---

# 📘 Auto-Generated Documentation

"""

    for filename, content in source_files:
        print(f"🧠 Generating docs for {filename}...")
        doc = generate_doc(content, filename)
        all_docs += f"\n\n## {filename}\n\n{doc}\n"

    os.makedirs(os.path.dirname(OUTPUT_DOC_PATH), exist_ok=True)
    with open(OUTPUT_DOC_PATH, "w") as f:
        f.write(all_docs)

    print(f"✅ Documentation written to: {OUTPUT_DOC_PATH}")

if __name__ == "__main__":
    main()
