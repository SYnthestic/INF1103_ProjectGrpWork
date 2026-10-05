# SME Green Grant Eligibility & Scope-3 Compliance Auditor

A terminal app that takes an SME's details and a free-text upgrade proposal, uses an AI model to classify the proposal under the GHG Protocol, then applies deterministic Python rules to decide grant eligibility and calculate the subsidy.

## How it is organised

| File | Role |
|---|---|
| `main.py` | Menu loop that ties the layers together |
| `io_manager.py` | All user input, validation and screen output |
| `ai_manager.py` | Sends the proposal to the AI API and returns a validated JSON result |
| `logic_manager.py` | Eligibility checks, grant matching and subsidy maths (no AI) |
| `data_manager.py` | Saving and loading records as JSON |

The project uses plain functions only (no classes).

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
2. Confirm your `Dockerfile` contains these two lines (add them if missing):

   ```dockerfile
   ENV SME_DATA_DIR=/app/data
   ENV PYTHONDONTWRITEBYTECODE=1
   ```

3. Build the image (from the project folder):

   ```
   docker build -t sme-grant-auditor .
   ```

4. Create and run the container. The `-it` flag is required because the app asks for input:

   ```
   docker run -it --name sme-auditor --env-file .env -v "C:\SME_Grant_Data:/app/data" sme-grant-auditor
   ```

   Replace `C:\SME_Grant_Data` with any folder on your computer where saved files should go.
   On Mac/Linux use a path such as `"$HOME/SME_Grant_Data:/app/data"`.

5. Next time, reuse the same container:

   ```
   docker start -ai sme-auditor
   ```

6. After changing code, `.env` or `requirements.txt`, recreate it:

   ```
   docker rm sme-auditor
   docker build -t sme-grant-auditor .
   docker run -it --name sme-auditor --env-file .env -v "C:\SME_Grant_Data:/app/data" sme-grant-auditor
   ```

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

## Step 4: Try a sample run

At the menu choose **1 (Start)** and enter:

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

Other menu options: **2** save, **3** load, **4** view records, **5** and **6** re-run the AI and logic steps on the latest record.

## Where saved files go

- Plain Python: `SME_Grant_Data` in your user folder (for example `C:\Users\<you>\SME_Grant_Data`).
- Docker: the folder you mounted with `-v`.
- To choose another location, set the environment variable `SME_DATA_DIR`.

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
| Code changes have no effect in Docker | The image still holds the old code. Rebuild and recreate the container (Step 3, Option A, item 6). |
| Filename rejected when saving | Use a plain name such as `Save1`, with no `/`, `\` or other special characters. |