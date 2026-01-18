# Telegram Post Manager Bot

A robust Telegram bot for managing channels, creating posts with file attachments/links, multi-category organization, and auto-deleting content.

## Features

*   **Advanced Post Creation**: Upload files (with passwords!) or share deep links.
*   **Secure Links** 🔒: Post IDs are obfuscated (`start=XyZ...`) to prevent guessing. Strict mode enabled.
*   **Force Subscribe** 🔐: Require users to join specific channels before accessing content.
*   **Broadcasting** 📢: Send messages to all users or filter by specific criteria.
*   **User Management** 👥: View user stats, ban/unban users, and track activity.
*   **Categories**: Organize posts with multi-select tags (e.g., "Action", "Drama").
*   **Auto-Delete** ⏱️: Content self-destructs after a set time (customizable per post).
*   **Advanced Search** 🔎: Find posts by ID, generic text, or filters.
*   **Persistence**: Uses SQLite (`bot.db`) for robust data handling.
*   **Admin Dashboard**: Full management UI within Telegram.

## Prerequisites

*   Python 3.9 or higher
*   A Telegram Bot Token (from [@BotFather](https://t.me/BotFather))

## Installation

1.  **Clone the repository** (or download files):
    ```bash
    git clone https://github.com/your-username/tg-post-bot.git
    cd tg-post-bot
    ```

2.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

## Configuration

1.  **Create `.env` file**:
    Rename `.env.example` to `.env` (or create a new one) and add your credentials:

    ```ini
    # Your Bot Token from BotFather
    TELEGRAM_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11

    # Your Telegram User ID (get it from @userinfobot)
    # Only this user can access the Admin Dashboard
    ADMIN_ID=123456789

    # (Optional) Main Channel ID for posting updates
    MAIN_CHANNEL_ID=-1001234567890
    ```

## Usage

1.  **Start the Bot**:
    ```bash
    python bot.py
    ```

2.  **Access Dashboard**:
    *   Open your bot in Telegram.
    *   Send any message or `/start`.
    *   If you are the `ADMIN_ID`, you will see the **Admin Dashboard**.
    
    **New Dashboard Features**:
    - **📢 Broadcast**: announcement tools.
    - **👥 Users**: Manage banned/active users.
    - **⚙️ Settings**: Configure Templates, Help Links, and Force Subscribe channels.
    - **💾 Backup**: Export your database instantly.

3.  **Create Content**:
    *   Use the **➕ Create Post** menu to upload files or create links.
    *   **Timer**: Set a custom auto-delete timer for each post.
    *   **Secure Link**: The bot generates a safe, obfuscated link for you to share.

## Project Structure

*   `bot.py`: Main entry point.
*   `handlers/`: Contains logic for Admin, User, Manager, Broadcast, and Settings.
*   `storage.py`: Handles SQLite database operations.
*   `config.py`: Configuration loader.


