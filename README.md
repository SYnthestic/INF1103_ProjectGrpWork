# SME Green Grant Eligibility & Scope-3 Compliance Auditor

A terminal app that takes an SME's details and a free-text upgrade proposal, uses an AI model to classify the proposal under the GHG Protocol, then applies deterministic Python rules to decide grant eligibility and calculate the subsidy.

## How it is organised

| File | Role |
|---|---|
| `main.py` | Menu loop that ties the layers together |
| `io_manager.py` | All user input, validation and screen output |
| `ai_manager.py` | Sends the proposal to the AI API and returns a validated JSON result |
| `logic_manager.py` | Eligibility checks, grant matching and subsidy maths (no AI) |
| `data_manager.py` | Saving and loading records, user accounts and audit history as JSON |

The project uses plain functions only (no classes).

---

## Quick start

1. Get the code (Step 1).
2. Put your OpenRouter key in a `.env` file (Step 2).
3. Run the app with Docker **or** plain Python (Step 3).
4. Create an account, log in, and try the sample audit (Steps 4 and 5).

The sections below walk through each step in detail.

---

## Before you start

You need:

1. **Git** or **GitHub Desktop**, to get the code.
2. An **OpenRouter API key** (free account at https://openrouter.ai, then create a key under *Keys*). The key is shown only once, so copy the whole thing.
3. **Either** Docker Desktop **or** Python 3.10 or newer (pick one path below).

An internet connection is required, because each audit makes a live AI call.

---

## Step 1: Get the code

With GitHub Desktop: *File → Clone repository*, choose `INF1103_ProjectGrpWork`, and pick a folder.

With git:

```
git clone <repository-url>
cd INF1103_ProjectGrpWork
```

## Step 2: Create your `.env` file

In the project folder (next to `main.py`), create a file named exactly `.env` containing one line:

```
OPENROUTER_API_KEY=sk-or-v1-paste-your-full-key-here
```

Rules that matter:

- Paste the **entire** key. Do not shorten it or leave `...` in it.
- No quotes and no spaces around `=`.
- Make sure the file is named `.env`, not `.env.txt` (Windows hides extensions by default).
- Never commit this file. It is listed in `.gitignore`.

---

## Step 3: Run it (choose ONE option)

### Option A: Docker

1. Start Docker Desktop and wait until it says the engine is running.
2. Build the image from the project folder (repeat this whenever the code changes):

   ```
   docker build -t sme-grant-auditor .
   ```

3. Pick a folder on your computer for the app's saved files, then run the container. Replace the part before the colon with your own folder:

   | Your computer | Command |
   |---|---|
   | Windows (CMD or PowerShell) | `docker run -it --name sme-auditor --env-file .env -v "C:\SME_Grant_Data:/app/data" sme-grant-auditor` |
   | Windows, `data` folder inside the project (PowerShell) | `docker run -it --name sme-auditor --env-file .env -v "${PWD}\data:/app/data" sme-grant-auditor` |
   | Mac / Linux | `docker run -it --name sme-auditor --env-file .env -v "$HOME/SME_Grant_Data:/app/data" sme-grant-auditor` |

   What the options do:

   - `-it` is required because the app asks for input.
   - `--env-file .env` passes in your API key.
   - `-v "<your folder>:/app/data"` links a folder on your computer to the folder the app saves into. The Dockerfile already points the app at `/app/data`, so your JSON files (saved records, `users.json`, `audit_history.json`) appear in your folder and survive the container being removed. **Do not leave this out**, or the files are lost.

4. Next time, reuse the same container:

   ```
   docker start -ai sme-auditor
   ```

5. After changing code, `.env` or `requirements.txt`, recreate it (your saved files stay in your folder):

   ```
   docker rm sme-auditor
   docker build -t sme-grant-auditor .
   ```

   then run the `docker run` command from item 3 again.

### Option B: Plain Python

1. Create and activate a virtual environment:

   ```
   python -m venv .venv
   .venv\Scripts\activate        (Windows)
   source .venv/bin/activate     (Mac/Linux)
   ```

2. Install the dependencies:

   ```
   pip install -r requirements.txt
   ```

3. Run:

   ```
   python main.py
   ```

If VS Code underlines `openai` as unresolved, choose the `.venv` interpreter via *Ctrl+Shift+P → Python: Select Interpreter*.

---

## Step 4: Create an account

The app opens on a login screen. Choose **2** to create an account (a username and a password of at least 8 characters with a letter and a digit), then choose **1** to log in. More detail is under *Accounts and login* below.

---

## Step 5: Try a sample run

Once logged in, choose **1 (Start)** at the menu and enter:

| Prompt | Sample input |
|---|---|
| Company name | `Apex Haulage & Freight Logistics Pte Ltd` |
| Industry | `Logistics` |
| Total revenue (SGD) | `8450000` |
| Employees | `38` |
| Local equity % | `85` |
| Proposal type | `1` |
| Proposal description | `We are replacing our current fleet of 6 diesel delivery vans with brand-new commercial electric vans and deploying two Level-2 smart charging stations at our Tuas depot.` |
| Baseline annual energy expenditure | `120000` |
| Estimated retrofit cost | `150000` |

The app then shows the AI audit and the grant decision, and asks whether to save. Because the AI estimates the energy reduction, exact figures can vary from run to run.

Other menu options: **2** save, **3** load, **4** view records, **7** and **8** re-run the AI and logic steps on the latest record, **9** view your past audits, **10** logout.

## Accounts and login

When the app starts you must log in (option **1**) or create an account (option **2**) before reaching the main menu.

- Usernames: 3-20 characters, letters/digits/underscore, not case-sensitive.
- Passwords: 8 to 64 characters, with at least one letter and one digit. Typing is hidden.
- Every audit completed with option **1** is saved automatically to your history. Option **9** lists your past audits and lets you open one in full. You only ever see your own audits. If the AI call fails (for example a missing API key or no internet), the result is shown but is **not** added to your history, so just run option **1** again.

Passwords are never stored. Each account stores a random salt and a salted SHA-256 hash (PBKDF2-HMAC-SHA256, 200,000 iterations), checked with a constant-time comparison.

| File | Contents |
|---|---|
| `users.json` | Usernames, salts and password hashes |
| `audit_history.json` | Each user's saved audits (inputs, AI result, decision) |

Both files are plain JSON and are **not** otherwise protected yet. They are in `.gitignore` and `.dockerignore`, so they are never committed or copied into the Docker image. They are saved with the app's other files (see *Where saved files go*). To reset all accounts, delete both files. A short-lived `users.json.lock` / `audit_history.json.lock` file may appear while the app is writing; it is removed automatically.

## Where saved files go

Everything the app saves goes into one folder, chosen by the `DATA_DIR` environment variable:

| What | Where inside that folder |
|---|---|
| `users.json`, `audit_history.json` | the folder itself |
| Records saved with option 2 (and PDF exports) | `records/<your username>/` - each user has a private folder, so users cannot load or overwrite each other's files |

Files saved by an older version directly in the folder are not shown to any user; move them into `records/<username>/` to keep using them.


- Docker: `/app/data` inside the container (set in the Dockerfile), which the `-v` option in Step 3 links to a folder on your computer. Keep `-v` in the `docker run` command, otherwise the files stay inside the container and are lost when it is removed.
- Plain Python: the folder you run `python main.py` from (normally the project folder), unless `DATA_DIR` is set. To keep the files in a separate folder, add a line such as `DATA_DIR=data` to your `.env` file. The folder is created automatically.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `AuthenticationError 401 - User not found` | The key in `.env` is wrong or shortened. Paste the full key. To check it loads: `python -c "import os; from dotenv import load_dotenv; load_dotenv(override=True); print(len(os.environ.get('OPENROUTER_API_KEY','')))"`. A real key is roughly 70 characters. |
| Result says `MANUAL_REVIEW` and scope `Unknown` | The AI call failed. Read `ai_reasoning_summary` in the AI Audit Result for the reason. |
| App hangs or `EOFError` in Docker | You forgot `-it` on `docker run`. |
| `container name "/sme-auditor" is already in use` | It already exists. Use `docker start -ai sme-auditor`, or `docker rm sme-auditor` to recreate it. |
| Docker errors mentioning `pipe` or `dockerDesktopLinuxEngine` | Docker Desktop isn't running. Start it. |
| Windows "Protected folder access blocked" | Controlled Folder Access is blocking writes to Documents/Desktop. Keep your data folder outside those (for example `C:\SME_Grant_Data`), or allow `docker.exe` in Windows Security. |
| Code changes have no effect in Docker | The image still holds the old code. Rebuild and recreate the container (Step 3, Option A, item 5). |
| Accounts or saved files disappear in Docker, or no `.json` files appear in your folder | The files were saved inside the container. Recreate the container with `-v "<your folder>:/app/data"` (Step 3, Option A, item 3). A container created earlier without it must be removed with `docker rm sme-auditor` first, and the image rebuilt if your Dockerfile is old. |
| `Could not save the new account` / an audit is not saved | Another copy of the app is writing at the same moment, or the data folder is not writable. Try again; if it keeps failing, check the folder's permissions (and delete a stale `*.lock` file in it). |
| Filename rejected when saving | Use a plain name such as `Save1`, with no `/`, `\` or other special characters. |