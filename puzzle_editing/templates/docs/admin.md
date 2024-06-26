There are a few features of PuzzUp that are only accessible to admins/superusers.

## Making yourself a superuser.

```
python manage.py createsuperuser
```

Now you have access to Django's `/admin/` site. You can edit most aspects of the data freely. Wield your power wisely.

## Assigning editors

To make a user an **editor**, find them under "Users" and give them the "**Can change round**" permission.

(There is no UI to do this outside of /admin, but you have to do this so few times that it's not high priority.)

## Defining statuses

This can be done in `status.py`.

## Status subscriptions

Each status subscription sends an email to a specific user whenever *any* puzzle enters a *specific* puzzle status.

(These are also completely invisible on the main website, which is maybe something we should fix.)

Some ways to use status subscriptions:

- Editors-in-chief who are in charge of assigning editors to puzzles when they need one can subscribe to the "Awaiting Editor" status. Then puzzle authors can set their puzzle to that status when they wanted an editor, and EICs will be notified.
- Similarly, the head factchecker and head copy editor can subscribe to the Needs Factcheck and Needs Copy Edits statuses
- For people who really wanted to testsolve puzzles, we gave them subscriptions to the Testsolving status so they would get an email whenever a puzzle entered testsolving.

## Site settings

Finally, there are a few "Site settings" that just look at the values associated with specific hardcoded keys in the codebase, so that you can change them without changing the code.

## Postprodding

PuzzUp allows you to export puzzle and hint metadata in the form of JSON or YAML files that can then be imported into your hunt repo.

We've also added the ability to automatically generate a React file based on a template. This hooks into the tph-template repo and automatically makes a commit in a new branch. To do so, you will need to set up the `HUNT_REPO` and `HUNT_REPO_URL` env variables to point to your local and remote Git repos, respectively.
