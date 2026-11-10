# SME Green Grant Eligibility & Scope-3 Compliance Auditor

A grant-eligibility auditor that takes an SME's details and a free-text upgrade proposal, uses an AI model to classify the proposal under the GHG Protocol, then applies deterministic Python rules to decide grant eligibility and calculate the subsidy. It runs two ways: as a **terminal app** (`main.py`) or as a **web app** built with Flask (`app.py`). Both use the same four managers.

## How it is organised

The program is object-oriented. The four managers from Part 1 are still the four main classes; they live in the `managers/` folder, and `main.py` wires them together.

| File | Main classes | Role |
|---|---|---|
| `app.py` | `create_app()` | **Flask entry point.** Builds the web app and hands it the same AI, Logic and Data managers the terminal app uses |
| `web/` | blueprints, `Workspaces`, `service` | **Web layer.** Routes (`pages.py` for HTML pages, `auth.py` and `audits.py` for the JSON API), the shared audit function, per-user in-memory records, `display.py` (how decisions, money and the AI audit are shown) and the templates in `web/templates/`. It contains no business logic, only calls into the managers |
| `main.py` | `Application` | The controller: runs the login screen and menu and passes data between the managers. The only file that knows about all four. Managers are handed to it, so tests can pass in doubles |
| `session.py` | `Session` | What one logged-in user is working on (records in memory, the current file name, whether there are unsaved changes). Created at login and discarded at logout |
| `managers/io_manager.py` | `IOManager`, `Terminal`, `InputValidator`, `PaperPrinter` | **I/O manager.** All user input, validation and screen output |
| `managers/ai_manager.py` | `AIManager`, `AIClient` (abstract), `OpenRouterClient`, `AuditResponseParser` | **AI manager.** Sends the proposal to the AI API and returns a validated JSON result. Depends on the `AIClient` interface, so another provider (or a test fake) can be plugged in |
| `managers/logic_manager.py` | `LogicManager`, `DecisionEngine`, `EligibilityRule` (abstract, 13 rules), `GrantScheme` (abstract, 4 schemes), `DecisionAdjuster`, `PasswordHasher`, `AesGcmCipher`, `RuleConfig`, `AccessPolicy` | **Logic manager.** Eligibility rules, grant matching, subsidy maths, password hashing, AES-256-GCM encryption of the data files and who may use the admin console (no AI). A new rule or scheme is a new subclass; the engine does not change. The thresholds the rules use are a `RuleConfig`, so changing them needs no code change |
| `managers/data_manager.py` | `DataManager`, `JsonStore`, `FilenameRules` | **Data manager.** Saving and loading records, user accounts, audit history and the grant rule thresholds as JSON; archiving deleted accounts |
| `report_exporter.py` | `ReportExporter` (abstract), `PdfReportExporter`, `ReportTheme`, `ReportContent` | PDF report drawing, kept separate from storage. The Data Manager only knows the `ReportExporter` interface |
| `models.py` | `Proposal` (abstract), `EquipmentProposal`, `ReportingProposal`, `ApplicationRecord`, `RecordSections`, `PlaceholderKeywords`, `FileCipher` (interface), `PlainFileCipher` | Small shared domain classes with no I/O. Any manager may import them |
| `sme_interface_stores/sme_interface_gui.py` | `InterfaceArt` | Screen art: menus, banners and the floppy-disk prompts. Used only by the I/O manager |
| `sme_interface_stores/buttons.py` | `ButtonPanel` | The clickable buttons. Used only by the I/O manager |
| `tests/` | | Automated tests, including ones that fail if a manager imports another manager or procedural code reappears |

The managers never import each other and only the I/O manager prints or asks for input. Data flows one way: the I/O manager collects and checks the input, the AI manager turns the narrative into a JSON audit, the logic manager decides, then the result goes to the data manager to be stored and back to the I/O manager to be shown.

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

In the project folder (next to `main.py`), copy `.env.example` to a new file named exactly `.env` (or create it yourself) containing two lines:

```
OPENROUTER_API_KEY=sk-or-v1-paste-your-full-key-here
DATA_ENCRYPTION_KEY=paste-the-generated-key-here
```

`DATA_ENCRYPTION_KEY` is required: every data file is encrypted with it and the app will not start without it (see *Data encryption* below). Generate one and paste the printed line into `.env`:

```
python main.py --generate-key
```

With Docker only (no Python installed), build the image first (Step 3) and run `docker run --rm sme-grant-auditor python main.py --generate-key`.

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

Other menu options: **2** save, **3** load, **4** view records, **7** and **8** re-run the AI and logic steps on the latest record, **5** change one detail of a record, **6** delete a record, **9** view your past audits (filter them, open one in full and export it as a PDF report), **10** logout, **11** admin console (administrators only, see below). Options 5 and 6 change the records in memory only; use option 2 to save. If the file already exists, option 2 asks whether to **add** to it, **replace** it (use this after deleting a record) or cancel. To back out of options 2 and 3, press Enter without typing a file name.

If you choose **0** (exit) or **10** (logout) while you have records that are not saved, the app asks whether to save first. Answer **n** to leave without saving, or **y** to save; if you then cancel the save, you are taken back to the menu with your records still there.

---

## Step 6 (optional): Run the web version

The same audits are available in a browser. Pick **one** option.

### Option A: Plain Python

1. Complete Step 2 (`.env` with your OpenRouter key) and Step 3, Option B (virtual environment and `pip install -r requirements.txt`).
2. Add a secret key for login cookies to your `.env`:

   ```
   FLASK_SECRET_KEY=any-long-random-string
   ```

   Generate one with `python -c "import secrets; print(secrets.token_hex(32))"`. Without it the app makes a new random key every time it starts, so everyone is logged out whenever the server restarts. There is no fixed fallback key in the code, because anyone who read it could forge a login.
3. Start the development server:

   ```
   python -m flask --app app run --debug
   ```

4. Open http://127.0.0.1:5000/ and register an account, then log in. `http://127.0.0.1:5000/health` returns `{"status": "ok"}` if the server is up.
5. Stop it with `Ctrl+C`.

`python -m flask` works even when the `flask` command is not on your PATH. Debug mode reloads the server on every code change and shows an interactive error page. It is only on when you ask for it (`--debug` here, or `FLASK_DEBUG=1` with `python app.py`). **Records held in memory are lost on each reload**, so save to a file before editing code. Never use `--debug` on a shared or public machine.

### Option B: Docker

The image still starts the terminal app by default. To run the web version instead, override the command and publish the port:

```
docker build -t sme-grant-auditor .
docker run --rm -p 5000:5000 --env-file .env -v "C:\SME_Grant_Data:/app/data" sme-grant-auditor gunicorn -w 1 -b 0.0.0.0:5000 "app:create_app()"
```

Then open http://localhost:5000/. On Mac/Linux replace the `-v` path with `"$HOME/SME_Grant_Data:/app/data"`.

- Use **one** worker (`-w 1`). Each user's records in memory live inside the server process, so several workers would each have their own separate copy.
- `-it` is not needed, because the web version does not read from the keyboard.
- Keep the `-v` option, or the accounts and saved files are lost when the container is removed.
- Put `FLASK_SECRET_KEY=...` in the same `.env` file, since `--env-file` passes it in.

### What the web version offers

| Page | What it does | Terminal equivalent |
|---|---|---|
| Register / Log in / Log out | Accounts, using the same `users.json` and the same rules as the terminal: usernames 3-20 letters, digits or `_` (not case-sensitive), passwords 8-64 characters with a letter and a digit | Login screen, option 10 |
| New audit | Form with dropdowns for industry and grant (each has an "Others" box that appears when chosen). Runs the AI and Logic managers, saves the audit to your history and keeps the record in memory | Option 1 |
| Records | Lists the records in memory, with Edit and Delete buttons | Options 4, 5, 6 |
| Save to JSON / Pull from JSON | Saves to or loads from your private `records/<username>/` folder. A blank file name cancels, and loading over unsaved records asks first | Options 2, 3 |
| Run AI Manager (only) / Run Logic Manager (only) | Re-runs one step on the latest record | Options 7, 8 |
| History | Lists your past audits with a coloured decision and the subsidy. Opening one shows the decision in plain English (green approved, amber review, red rejected) with the subsidy, matched schemes, reasons and recommendations, then the AI audit, the application and the thresholds it was decided with. Each can be downloaded as a PDF | Option 9 |
| Log out | Warns if you have unsaved records and lets you save or leave without saving | Options 0 and 10 |

The form checks numbers with the same limits as the terminal: revenue above 0, a whole number of employees above 0, local equity above 0 and at most 100, and for equipment proposals a baseline energy spend and retrofit cost above 0. Values the browser lets through, such as `1e309`, are refused by the server.

Things that differ from the terminal app:

- Records in memory are kept **per user, in the server process**. They are lost when the server restarts, so save to a file if you want to keep them.
- Saving again to the file you are already using replaces it without asking. Saving to a different existing file asks you to add, replace or cancel.
- The Pull from JSON page lists your saved files in a dropdown instead of asking you to type a name.

### JSON API

The same audit logic is available without the pages. Log in first; the session cookie is used for the other calls.

| Method and path | Purpose |
|---|---|
| `POST /api/register` | Body `{"username": "...", "password": "..."}`. 201 on success, 400 if the username or password breaks the account rules, 409 if taken |
| `POST /api/login` | Same body. 200 on success, 401 otherwise |
| `POST /api/logout` | Ends the session |
| `POST /api/audits` | Body is one application record (same keys as the saved records). Numbers must be JSON numbers within the terminal's limits (revenue above 0, a whole number of employees above 0, local equity above 0 and at most 100, costs 0 or more); otherwise 400. Returns the saved audit |
| `GET /api/audits` | Your audits |
| `GET /api/audits/<id>` | One of your audits (404 for anyone else's) |

Example in PowerShell:

```
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:5000/api/register -ContentType "application/json" -Body '{"username":"tester","password":"Test1234!"}'
```

## How grant decisions are made

The AI only classifies the proposal (scope, estimated energy reduction, any exclusion keywords). The decision and the subsidy come from fixed Python rules in `managers/logic_manager.py`. They are checked in this order, and the first one that applies decides:

| # | Condition | Decision |
|---|---|---|
| 1 | Exclusion keywords found (e.g. "second-hand"), or the intervention is "Fossil Fuel Modification" | `MANUAL_EXCLUSION_REVIEW` |
| 2 | Local shareholding under 30%, or annual revenue over SGD 100 million | `REJECT_NON_SME` |
| 3 | The AI analysis failed (for example no API key or no internet) | `MANUAL_REVIEW` |
| 4 | ESG Reporting proposal with a fee over SGD 0 | `PRE_APPROVED_SRG` (30% of the fee, up to SGD 150,000) |
| 5 | Equipment proposal with no baseline energy spend, or ESG proposal with no fee | `MANUAL_REVIEW` |
| 6 | The AI could not classify a scope | `MANUAL_REVIEW` |
| 7 | Lifetime abatement over 350 tonnes **and** energy reduction of at least 10% | `PRE_APPROVED_TIER_1_ADVANCED` (70% of baseline spend, up to SGD 350,000) |
| 8 | Scope-1 and energy reduction of at least 20% | `PRE_APPROVED_TIER_1` (70% of baseline spend, up to SGD 30,000) |
| 9 | Any scope and energy reduction of at least 15% | `PROVISIONAL_APPROVAL_TIER_2` (50% of baseline spend, up to SGD 20,000) |
| 10 | Energy reduction from 10% to under 15% | `MANUAL_REVIEW` |
| 11 | Energy reduction under 10% | `REJECT_LOW_IMPACT` |

The percentages and the 350-tonne limit above are the defaults. An administrator can change them in the admin console (see *Administrator console*); every new decision then uses the new values, and each saved audit records the thresholds it was decided with.

Equipment subsidies (rows 7 to 9) are never larger than the retrofit cost you entered. The grant you pick when entering the application does not change the decision; if the proposal matched a different scheme, a recommendation says so.

In the code each condition is one small `EligibilityRule` subclass in `managers/logic_manager.py` (some rows above are split into two rules, for 13 in all). The `DecisionEngine` runs them in the order given by `DecisionEngine.with_default_rules()`, and the first rule that returns a decision wins. A new rule is a new subclass added to that list, with a matching test in `tests/test_logic_manager.py`; the engine itself does not change.

## Accounts and login

When the app starts you must log in (option **1**) or create an account (option **2**) before reaching the main menu.

- Usernames: 3-20 characters, letters/digits/underscore, not case-sensitive.
- Passwords: 8 to 64 characters, with at least one letter and one digit. Typing is hidden.
- Every audit completed with option **1** is saved automatically to your history. Option **9** lists your past audits, lets you filter the list (by decision, or by company name), and open one in full. After opening one you can export it as a PDF report (final decision, AI analysis and reasons) saved in your own `records/<your username>/` folder; this needs `reportlab`, which is in `requirements.txt`. The number of saved audits is shown right after you log in. You only ever see your own audits. If the AI call fails (for example a missing API key or no internet), the result is shown but is **not** added to your history, so just run option **1** again.

Passwords are never stored. Each account stores a random salt and a salted SHA-256 hash (PBKDF2-HMAC-SHA256, 200,000 iterations), checked with a constant-time comparison.

| File | Contents |
|---|---|
| `users.json` | Usernames, salts and password hashes |
| `audit_history.json` | Each user's saved audits (inputs, AI result, decision) |

Both files are encrypted with AES-256-GCM (see *Data encryption*). They are in `.gitignore` and `.dockerignore`, so they are never committed or copied into the Docker image. They are saved with the app's other files (see *Where saved files go*). To reset all accounts, delete both files. A short-lived `users.json.lock` / `audit_history.json.lock` file may appear while the app is writing; it is removed automatically.

## Administrator console

Set `ADMIN_USERNAME` in your `.env` file (for example `ADMIN_USERNAME=admin`, see `.env.example`). On the next start the app asks you to choose that account's password before anyone can log in, and nobody else can register that name. When an administrator logs in, the main menu shows option **11. Admin Console**:

| Option | What it does |
|---|---|
| 1 | List users: username, role, number of saved audits, creation date. Password hashes are never shown |
| 2 | Create a user, choosing the role (`user` or `admin`) and a password |
| 3 | Reset a user's password |
| 4 | Change a user's role (promote to admin or back to user) |
| 5 | Delete a user. You must type their username to confirm. The login is removed, but their data is **archived, not destroyed**: it moves to `archive/<username>_<date-time>/` with `account.json` (account details without the password hash), `audit_history.json` and their `records/` folder |
| 6 | View the grant rule thresholds |
| 7 | Change one threshold. The new value is checked first: percentages must be above 0 and at most 100, and must not decrease (minimum <= provisional <= fast track); the tonnes limit must be above 0. An invalid value is explained and nothing changes |
| 8 | Reset all thresholds to the defaults |

To keep at least one administrator, the `ADMIN_USERNAME` account can never be demoted or deleted, and no administrator can demote or delete their own account. Threshold changes are saved to `rules_config.json` with who changed them and when, and are picked up at every login. If that file is damaged or holds invalid values, the app shows a warning and uses the defaults.

The admin console is in the terminal app only. The web version uses the same accounts and thresholds: its register page refuses the `ADMIN_USERNAME` name, and its grant decisions use the thresholds saved here.

## Data encryption

Every JSON data file the app saves is encrypted with **AES-256-GCM**: `users.json`, `audit_history.json`, `rules_config.json`, the record files in `records/` and everything in `archive/`. `app.log` and exported PDFs are not encrypted (you need to read them).

- **The key.** `DATA_ENCRYPTION_KEY` in `.env`: 32 random bytes written as base64. Create one with `python main.py --generate-key`. It is never committed (`.env` is in `.gitignore`), never stored in a data file and never shown by the app. **If it is lost, the files cannot be opened again**, so keep a copy somewhere safe.
- **Fails closed.** Without a valid key the app (terminal and web) refuses to start, so data is never saved unencrypted by mistake.
- **Tamper-evident.** Each file holds a marker (`SMEENC1`), a fresh random 12-byte nonce, the encrypted JSON and a 16-byte authentication tag. A wrong key or any changed byte is detected; the file is then left untouched and the app reports it instead of loading it.
- **Each teammate** can use their own key, because each person's data folder stays on their own computer. Share a key (privately, never in the repo or group chat) only if you also share a data folder.
- **Existing plain files** (saved before encryption was added) are not trusted automatically. Encrypt them once, while the app is not running:

  ```
  python main.py --encrypt-existing-data
  ```

  Docker: `docker run --rm --env-file .env -v "<your folder>:/app/data" sme-grant-auditor python main.py --encrypt-existing-data`

- **Tests and CI** create a throwaway key for each test, so no secret is needed on GitHub.

The encryption code is `AesGcmCipher` in `managers/logic_manager.py`, which implements the `FileCipher` interface in `models.py`. `main.py` passes it to the `DataManager`, whose `JsonStore` encrypts on every save and decrypts on every load without knowing which cipher it has.

## Where saved files go

Everything the app saves goes into one folder, chosen by the `DATA_DIR` environment variable:

| What | Where inside that folder |
|---|---|
| `users.json`, `audit_history.json`, `rules_config.json` | the folder itself |
| Records saved with option 2 (and PDF exports) | `records/<your username>/` - each user has a private folder, so users cannot load or overwrite each other's files |
| Data of deleted accounts | `archive/<username>_<date-time>/` |

Files saved by an older version directly in the folder are not shown to any user; move them into `records/<username>/` to keep using them.


- Docker: `/app/data` inside the container (set in the Dockerfile), which the `-v` option in Step 3 links to a folder on your computer. Keep `-v` in the `docker run` command, otherwise the files stay inside the container and are lost when it is removed.
- Plain Python: the folder you run `python main.py` from (normally the project folder), unless `DATA_DIR` is set. To keep the files in a separate folder, add a line such as `DATA_DIR=data` to your `.env` file. The folder is created automatically.

---

## Tests and continuous integration

The project has an automated [pytest](https://docs.pytest.org/) suite (`pytest` is in `requirements.txt`) that covers the grant rules, the AI output cleaning, accounts, saved files and the class design itself. It never calls the AI or touches your real data.

```
python -m pytest -v
```

To check the code style as well, install [ruff](https://docs.astral.sh/ruff/) (`pip install ruff`) and run `ruff check .`.

Every push and pull request on GitHub runs the same checks automatically (`.github/workflows/ci.yml`): lint, the tests (`python -m pytest`) on Python 3.11, 3.12 and 3.13, then a Docker build whose image runs the tests again. A red cross on a commit means a check failed; click it to see which one. When everything passes on `main`, a final job publishes the Docker image to the GitHub Container Registry as `ghcr.io/<owner>/<repo>` (tags `latest` and the commit id); pull requests never publish. `requirements.txt` gives each package a version range (a lower and an upper bound) so a future major release cannot break a fresh install.

`tests/test_logic_sample_ai_responses.py` is the stand-alone check of the Logic Manager: it feeds hardcoded sample AI responses (raw JSON text) to `logic_manager`, needs no API key or internet (a guard fails the test if a network connection is attempted), and can be run on its own with `python -m pytest tests/test_logic_sample_ai_responses.py`.

You can also run the tests inside the Docker image. Build it first, then run either the stand-alone Logic Manager script or all the tests:

```
docker build -t sme-grant-auditor .
docker run --rm sme-grant-auditor python -m pytest tests/test_logic_sample_ai_responses.py
docker run --rm sme-grant-auditor python -m pytest
python -m flask --app app run --debug
```

The tests live in `tests/`, one file per manager (`test_logic_manager.py`, `test_ai_manager.py`, `test_data_manager.py`, `test_io_manager.py`, `test_main_flows.py` for the controller) plus `test_password_hasher.py` for password hashing on its own, `test_rule_config.py` for the adjustable thresholds, `test_admin.py` for the admin console, and `test_architecture.py`. The web layer has its own files: `test_web.py` (health, accounts and the JSON API), `test_pages.py` (the HTML forms), `test_records.py` (records in memory, save, load, edit, delete), `test_pdf.py` (PDF download), `test_web_admin.py` (the web pages respect the admin name and the saved thresholds) and `test_web_security.py` (the terminal's account rules, no fixed secret key, debugger off by default) and `test_web_display.py` (how decisions are shown) and `test_web_numbers.py` (bad numbers such as `nan`, `inf` or `1e309` are refused on every page and the API). They use a temporary data folder and a fake AI, so they never call the AI or touch your real data.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `flask : The term 'flask' is not recognized` | The `flask` command is not on your PATH. Use `python -m flask --app app run --debug`, with the virtual environment activated |
| `ModuleNotFoundError: No module named 'flask'` | Flask is not installed in the active environment. Run `python -m pip install -r requirements.txt` |
| Browser shows "Not Found" at `/` | Check that you are running the latest `app.py`. `/` redirects to the login page. `/health` is the quick check |
| Pages look old after a change | Hard refresh with `Ctrl+Shift+R`. Templates are cached by the browser |
| Records vanish from the Records page | The server restarted (debug reload, or you stopped it). Records in memory are lost on restart, so save to a file first |
| Docker web version: page will not load | Check that you used `-p 5000:5000` and the `gunicorn ... 0.0.0.0:5000` command. Binding to `127.0.0.1` inside the container is not reachable from your computer |
| `gunicorn` fails to start on Windows | Gunicorn runs only on Linux and Mac. It is installed by `requirements.txt` so the Docker image has it; on Windows use the Flask command locally and gunicorn inside Docker |
| Logged out unexpectedly | The `FLASK_SECRET_KEY` changed between runs, which invalidates the cookies. Set a fixed value in `.env` |
| `AuthenticationError 401 - User not found` | The key in `.env` is wrong or shortened. Paste the full key. To check it loads: `python -c "import os; from dotenv import load_dotenv; load_dotenv(override=True); print(len(os.environ.get('OPENROUTER_API_KEY','')))"`. A real key is roughly 70 characters. |
| Result says `MANUAL_REVIEW` and scope `Unknown` | The AI call failed. Read `ai_reasoning_summary` in the AI Audit Result for the reason. |
| App hangs or `EOFError` in Docker | You forgot `-it` on `docker run`. |
| `container name "/sme-auditor" is already in use` | It already exists. Use `docker start -ai sme-auditor`, or `docker rm sme-auditor` to recreate it. |
| Docker errors mentioning `pipe` or `dockerDesktopLinuxEngine` | Docker Desktop isn't running. Start it. |
| Windows "Protected folder access blocked" | Controlled Folder Access is blocking writes to Documents/Desktop. Keep your data folder outside those (for example `C:\SME_Grant_Data`), or allow `docker.exe` in Windows Security. |
| Code changes have no effect in Docker | The image still holds the old code. Rebuild and recreate the container (Step 3, Option A, item 5). |
| Accounts or saved files disappear in Docker, or no `.json` files appear in your folder | The files were saved inside the container. Recreate the container with `-v "<your folder>:/app/data"` (Step 3, Option A, item 3). A container created earlier without it must be removed with `docker rm sme-auditor` first, and the image rebuilt if your Dockerfile is old. |
| `Could not save the new account` / an audit is not saved | Another copy of the app is writing at the same moment, or the data folder is not writable. Try again; if it keeps failing, check the folder's permissions (and delete a stale `*.lock` file in it). |
| `The app cannot start: DATA_ENCRYPTION_KEY is not set` | Add the key to `.env` (Step 2). Generate one with `python main.py --generate-key` |
| `... cannot be decrypted: the key ... is wrong, or the file was modified` | `DATA_ENCRYPTION_KEY` is not the key these files were saved with. Put the original key back. Nothing was changed or deleted |
| `... is not encrypted yet` | Data saved before encryption was added. Run `python main.py --encrypt-existing-data` once |
| Filename rejected when saving | Use a plain name such as `Save1`, with no `/`, `\` or other special characters. |

python -m flask --app app run --debug