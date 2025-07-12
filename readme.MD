# Discord Counter Bot

A powerful and intuitive Discord bot for creating, managing, and tracking multiple counters within organized groups. Built with Python using the `py-cord` library, this bot features a fully interactive UI with buttons and persistent data storage using Google Sheets.

*(Replace this with a real screenshot URL of your bot in action. A good format is `![Bot in Action](URL_TO_YOUR_SCREENSHOT)`)*

---

##  Core Features

*   **Slash Commands:** Modern and easy-to-use commands for all functionalities.
*   **Counter Groups:** Organize your counters into unlimited, user-defined groups (e.g., "Game Wins," "Daily Tasks," "Project Milestones").
*   **Interactive UI:** Manage counters instantly without typing commands. Each counter list comes with buttons to increase, decrease, or delete entries.
*   **Pagination:** Easily browse through large groups of counters with interactive "Previous" and "Next" page buttons.
*   **Persistent Storage:** Your data is safe! The bot uses a Google Sheet as a free and reliable database, so your counters are never lost, even if the bot restarts.
*   **Smart Autocomplete:** Commands provide helpful, context-aware suggestions for group and counter names as you type.

---

##  Commands

All commands are initiated with `/`.

### `/listgroups`

Lists all available counter groups that have been created in the server.

### `/listcounters [group]`

Displays an interactive, paginated list of all counters within a specified group.
*   **`group` (Required):** The name of the group you want to view. Autocomplete will suggest existing groups.

### `/createcounter [group] [name]`

Creates a new counter with a starting value of 1 within a specified group.
*   **`group` (Required):** The name of the group to add the counter to. You can type a new name to create a new group.
*   **`name` (Required):** The name of the new counter.

### `/deletecounter [group] [name]`

Deletes a specific counter from a group.
*   **`group` (Required):** The group the counter belongs to.
*   **`name` (Required):** The name of the counter to delete. Autocomplete will suggest counters from the selected group.

---

##  Setup & Installation (For Self-Hosting)

To run your own instance of this bot, follow these steps.

### 1. Prerequisites

*   Python 3.11+
*   A Git client
*   A Discord account with permissions to create applications.

### 2. Create a Discord Bot Application

1.  Go to the [Discord Developer Portal](https://discord.com/developers/applications).
2.  Click **"New Application"** and give it a name.
3.  Navigate to the **"Bot"** tab and click **"Add Bot"**.
4.  Click **"Reset Token"** to get your bot's token. **Keep this token secret.** You will need it for the `DISCORD_TOKEN` environment variable.

### 3. Set Up Google Cloud & Sheets for Storage

This is the most involved step, but you only have to do it once.

1.  **Create the Google Sheet:**
    *   Go to [sheets.google.com](http://sheets.google.com) and create a new, blank spreadsheet.
    *   Name it **exactly** `DiscordCounterBotData`.
    *   In the first row, create the following headers: Cell A1: `guild_id`, Cell B1: `group_name`, Cell C1: `counter_name`, Cell D1: `value`.
2.  **Create a Google Cloud Project:** Go to the [Google Cloud Console](https://console.cloud.google.com/) and create a new project.
3.  **Enable APIs:** In your new project, search for and **Enable** these two APIs: `Google Drive API` and `Google Sheets API`.
4.  **Create a Service Account:** In the console, search for "Service Accounts". Click **"+ Create Service Account"**. Give it a name, grant it the role of **`Basic` → `Editor`**, and click "Done".
5.  **Generate a JSON Key:** Click on the service account you just created. Go to the **"Keys"** tab → **"Add Key"** → **"Create new key"**. Select **JSON** and click "Create". A `.json` file will download. **This file is your password.**
6.  **Share the Sheet:** Open the downloaded `.json` file and copy the `"client_email"` address. Go to your Google Sheet, click **"Share"**, and paste the email address. Give it **Editor** permissions.

### 4. Repository Setup

# Clone the repository
git clone https://github.com/your-username/your-repo-name.git
cd your-repo-name

# Install the required Python packages
pip install -r requirements.txt
Use code with caution.
Markdown
5. Environment Variables
For local testing, create a file named .env in the root of the project and add the following:
Generated env
DISCORD_TOKEN=Your_Bot_Token_Goes_Here
GOOGLE_CREDENTIALS_JSON='<paste the entire contents of your downloaded .json key file here on a single line>'
Use code with caution.
Env
6. Run Locally
Generated bash
python bot.py
Use code with caution.
Bash
 Deployment & Third-Party Integrations
This bot is designed to run 24/7 on a cloud hosting platform. This project uses the following free-tier services:
1. Render (Application Hosting)
Role: Render serves as the main host for the Python application. It pulls the code directly from this GitHub repository and runs the bot.py script.
Setup: The bot is deployed as a Web Service on Render's free tier. The Flask web server included in the code opens a port, which allows Render's health checks to pass.
Environment Variables: Your DISCORD_TOKEN and GOOGLE_CREDENTIALS_JSON must be set in the Environment tab of your service on the Render dashboard.
2. Google Sheets (Persistent Database)
Role: Google Sheets acts as a free, simple, and permanent database for all counter data. Every time a counter is created, updated, or deleted, the bot makes a change to the spreadsheet.
Setup: Requires the Google Cloud setup detailed above. The bot authenticates using the GOOGLE_CREDENTIALS_JSON environment variable.
3. Site24x7 (Uptime & Keep-Alive Service)
Role: Render's free Web Service tier will "spin down" (go to sleep) after 15 minutes of inactivity. To prevent this, we need an external service to ping the bot's public URL regularly.
Setup: A free account on a service like Site24x7 (or UptimeRobot) is used.
A HTTP(s) Monitor is created.
The monitor's target URL is set to the public URL provided by Render (e.g., https://your-bot-name.onrender.com).
The check frequency is set to 10 minutes or less.
This periodic ping counts as "activity" and ensures Render keeps the bot running 24/7.