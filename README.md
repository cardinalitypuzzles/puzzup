# PuzzUp

A Django app for editing/testing puzzles for a puzzlehunt. Cloned from [PuzzLord](https://github.com/galacticpuzzlehunt/puzzlord), which was a reincarnate of [Puzzletron](https://github.com/mysteryhunt/puzzle-editing/).

# Design / How it works

Some goals and consequences of PuzzUp's design:

### Simplicity and low maintenance costs, with the goal of letting PuzzUp last many years without continuous development effort

- Few roles
- JavaScript dependence is minimized. When useful, use modern JS and don't try to support old browsers.
- To reduce code, rely on Django built-in features when possible.

### Connection between PuzzUp and hunt repo

- Generate postprodded files from Google Docs and commit directly to the repo
- Export metadata, partial answers, and hints directly to the hunt repo

### Permissiveness, which dovetails with simplicity, is OK because we generally trust our writing team

- Anybody can change the status of puzzles and add/remove themselves or other people to/from any puzzle-related role (author, discussion editor, factchecker, postprodder, spoiled).

### Spoiler safety

- Puzzles can have custom codenames, which PuzzUp will try to show to non-spoiled people.
- PuzzUp always shows you an interstitial and requires you to confirm that you would like to be spoiled. You cannot accidentally spoil yourself on puzzles or metas.

### Integration with external apps

- Auto-creates Google Sheets for brainstorming, testsolving, and factchecking
- Auto-creates Discord channels for puzzles
- Auto-creates Discord threads for testsolves

### Other workflow points

- Factchecking comes after postprodding
- Some additional useful puzzle statuses

# Installation

## Requirements

- Python 3.9
- poetry
- Postgres

## Local setup

Make sure you have **Python 3.9** and [**poetry**](https://python-poetry.org/docs/)
installed.

`cd` into the root of this repo

Install the **requirements**:

```
poetry shell    # Creates and activates virtualenv. Ctrl-D to quit.
poetry install  # Installs deps in poetry.lock.
```

Create a folder for **logs** to go in:

```
mkdir logs
```

Use Postgres to **create a new database**:

```
createdb -U postgres puzzup
```

Note: if you are on Ubuntu on Windows (WSL2), you may need to do the following:

```
sudo vim /etc/postgresql/12/main/pg_hba.conf  # swap 12 with your version of Postgres
# edit this line:
local   all             all                                     peer
# to read:
local   all             all                                     md5
```

Duplicate `.env.template` to a file called `.env`. You'll want to change the following secrets:

- `PUZZUP_SECRET` should be something long, random, and highly secure.
- `DATABASE_URL` should map to your local postgres, e.g. `postgres://postgres:password@localhost:5432/puzzup`

You can skip the other environment variables for now.

**Migrate** by running

```
./manage.py makemigrations
./manage.py migrate
```

Install pre-commit hooks (may need to `pip3 install pre-commit` first):

```
pre-commit install
```

Load user and group fixtures.

```
inv load-users
```

If all went well, run this to start the dev server:

```
./manage.py runserver
```

The local IP and port should be printed to stdout, and it should helpfully tell you that you're running Django 3.1.x.

### Server set-up

You only need to do this once, after you clone the repo and are setting it up for your team.

**Set the site password**

`SITE_PASSWORD` as an environment variable. (This is what you will give out to users to let them register accounts)

**Define the sender and reply-to email**

in `puzzle_editing/messaging.py`

**Define the ALLOWED_HOSTS**

in `settings/staging.py` and `settings/prod.py`

## Setting up the server

**Spin up server instance** and pull latest code

We used Heroku.

**Environment vars for integrating Discord**

- `DISCORD_APP_PUBLIC_KEY`
- `DISCORD_BOT_TOKEN`
- `DISCORD_CLIENT_ID`
- `DISCORD_CLIENT_SECRET`
- `DISCORD_GUILD_ID`

**Environment vars for integrating Google Drive**

- `PUZZUP_URL` = PuzzUp URL, for linking to PuzzUp from sheet
- `TESTSOLVING_FOLDER_ID` = top-level dir for testsolve spreadsheets
- `PUZZLE_DRAFT_FOLDER_ID` = top-level dir for puzzle drafts
- `FACTCHECKING_FOLDER_ID` = top-level dir for factcheck sheets
- `FACTCHECKING_TEMPLATE_ID` = Google Sheet ID of template to copy for factchecking

**Other enviornment variables**

- `BUILDPACK_SSH_KEY` = for integration with Hunt site repo
- `DATABASE_URL` = full path w/ credentials, to your DB
- `DJANGO_SETTINGS_MODULE` = `settings.prod`
- `HUNT_REPO` = path to Hunt repo. `/tmp/hunt` works.
- `POSTPROD_URL` = staging URl
- `PUZZUP_SECRET` = random string
- `SITE_PASSWORD` = needed for your users use to register
- `SSH_KEY_PATH` = Likely `~/.ssh/id_rsa`

**Install auth fixture**

If you're using Heroku, you can use `inv load-all-prod`. Otherwise, SSH into your PuzzUp server and run `./manage.py loaddata auth`.

## Installing packages

If you ever need to install more pip packages for this project, make sure you're in the poetry shell. Then just type

```
poetry add [package-name]
```

It'll automatically get added to the **pyproject.toml** and update **poetry.lock**.

# FAQ

## Why are things broken?

- Did you forget to go into `poetry shell`
- Did you forget to install all the requirements?
- Are you running python 2? If `python version` starts with 2, you might need to install python 3, or to swap `python` to `python3` at the beginning of your commands.

## How do I use `manage.py`?

- You can always run `python manage.py --help` to get a list of subcommands
- To create a superuser (so you can access the `/admin` page locally) run `python manage.py createsuperuser`
- If you get a warning (red text) about making migrations run `python manage.py migrate`

## Where are things?

The Django project (currently) has only one app, called "puzzle_editing". Most business logic and UI lives inside the `puzzle_editing` directory.

## Where are static files?

Static files (CSS etc.) live in `puzzle_editing/static`.

# Discord Integration

Puzzup integrates a fair bit with Discord, allowing for channels to be managed. To use it, there's a little bit of setup. This integration should be stable through version 9 of the Discord API.

## Setup

You will need to create a [Discord application here](https://discord.com/developers/applications).

- Set this application's **Interactions endpoint URL** to `https://your-puzzup-url/slashcommands`
- Under the OAuth2 section of your application, add this redirect url `http://your-puzzup-url/account/oauth2`
- Enable a bot for your application.
- Enable the Privileged Gateway Intents for your bot. This gives the bot certain permissions such as viewing the list of all members in the server.

Make a note of:

- your discord server ID (you can switch on Developer Mode and the right-click > Copy ID to do this; called a guild ID below)
- your bot's bot token
- your application's public key
- your application's client ID
- your application's client secret

Set necessary **Discord environment variables**. See above.

By default, `DISCORD_OAUTH_SCOPES` is set to `identify` only, since that is all the site needs at this time.

You'll need to add a bot to your server with the following permissions - the below link will do this for you, just add your client ID:

```
https://discord.com/api/oauth2/authorize?client_id=YOUR_CLIENT_ID&permissions=268446736&scope=applications.commands%20bot
```

- Manage channels - needed to rename, create and reorganise channels
- Manage roles - needed to override visibility for users and roles on puzzle channels
- Commands - needed for your users to be able to invoke the below slash commands

Finally, make a `POST` request to `https://discord.com/api/v9/applications/YOUR_APPLICATION_CLIENT_ID/guilds/YOUR_GUILD_ID/commands` with the below JSON payload, authorised with your bot token (Authorization: Bot BOT_TOKEN)

Alternately, you can instead make the `POST` request to `https://discord.com/api/v9/applications/YOUR_APPLICATION_CLIENT_ID/commands` and then wait up to an hour for commands to propagate. This will enable your commands globally, but there's really no need for this.

```json
{
  "name": "up",
  "description": "Interact with Puzzup",
  "options": [
    {
      "type": 1,
      "name": "create",
      "description": "Create a puzzle in Puzzup linked to the current channel"
    },
    {
      "type": 1,
      "name": "archive",
      "description": "Archive the current channel"
    },
    {
      "type": 1,
      "name": "info",
      "description": "Get information about the current channel's puzzle"
    },
    {
      "type": 1,
      "name": "url",
      "description": "Get the link for the current channel's puzzle"
    }
  ]
}
```

# Google Drive Integration

Puzzup supports auto-postprodding from Google Docs as well as auto-creating Sheets for puzzle brainstorming, testsolving, and factchecking. To make use of Google Drive integration, you will need to follow these steps:

1. Create a [service account](https://cloud.google.com/iam/docs/creating-managing-service-accounts) in Google Cloud.
2. Create a [service account key](https://cloud.google.com/iam/docs/creating-managing-service-account-keys). Download and save this JSON file to `credentials/drive-credentials.json`. (You will want to distribute this locally to each developer, as well as a copy on the production server.)
3. Invite the service account in order to access your Drive folders.
4. Set the appropriate **Google Drive environment variables** (see above).

## Autopostprod

The autopostprod feature takes a Google Doc and converts it into React code based on a provided template.
A number of assumptions are made, including the location of puzzle and solution templates (`puzzle_editing/utils.py`) and where to save assets, puzzles, and fixtures (`puzzle_editing/git.py`).

The process is roughly as follows:

1. Pass a Google Doc ID to the postprod form.
2. Download the HTML from Google Drive API.
3. Download any images and run postprocessing to downscale and optimize them (currently only PNG supported)
4. Run postprocessing on the HTML and convert to React style tsx, then insert into a template.
5. Save the file into the hunt repo.
6. Save a YAML fixture of puzzle metadata into the hunt repo.
7. Run pre-commit (if present) to auto-format the files.
8. Commit and push to a branch on the hunt repo.

Some changes are necessary to support a raw HTML format (e.g. gph-site) instead of React.

The process has a number of known issues, including poor error handling (timeouts or simultaneous requests often leave the repo in a dirty state, and need to be resolved by SSHing and manually fixing the git repo). Moving this into an async task, better error handling, and support for non-PNG images are open items.

# Credits

Forked from [PuzzLord](https://github.com/galacticpuzzlehunt/puzzlord), which is maintained by [@betaveros](https://github.com/betaveros). Lots of infrastructure by [@mitchgu](https://github.com/mitchgu). Many contributions from [@jakob223](https://github.com/jakob223), [@dvorak42](https://github.com/dvorak42), and [@fortenforge](https://github.com/fortenforge).

UI reskin by [Sandy Weisz](https://github.com/santheo). Lots of work by Discord improvements by [James Sugrono](https://github.com/jimsug).

Additional contributions by members of [teammate](https://github.com/teammatehunt).

Contains a lightly modified copy of [sorttable.js](https://kryogenix.org/code/browser/sorttable/), licensed under the X11 license.
