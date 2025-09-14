# text2cmd

A tool to convert natural language into shell commands using the Gemini API.

---

## Setup

1. Clone the repository:

    ```bash
    git clone https://github.com/Shankar-1212/text2cmd.git
    cd text2cmd
    ```

2. Create and activate a virtual environment:

    ```bash
    python -m venv venv
    source venv/bin/activate
    ```

3. Install in editable mode:

    ```bash
    pip install -e .
    ```
4. Setup api key
     ```bash
    echo "GEMINI_API_KEY=your_api_key_here" > .env
    ```
---

## Usage
 
 ```bash
    ask "list all files in current directory"
 ```

