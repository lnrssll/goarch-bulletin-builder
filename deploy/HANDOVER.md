# The bulletin website: what the church needs to know

Print this page, fill in the blanks, and keep it with the parish records. It's written so that someone who has never used the website can keep it going, or tell a helper what they need.

## What it is

A website that makes the Sunday bulletin: it downloads the readings from goarch.org, lets you fill in the hymns and upcoming services, and gives a booklet to print (one sheet, both sides, folded in half). Nothing needs to be installed: it works in any web browser, on a computer or a phone.

| | |
|---|---|
| Web address | ______________________________________ |
| Password | kept at ______________________________ (not written here) |
| People who know the password | ______________________________________ |
| Set up by | ____________________ phone/email ____________________ |

## Every week

1. Open the web address and log in.
2. Click **Open this Sunday**.
3. **Readings:** click **Download the readings**. If goarch.org doesn't answer, try again later, or click **type them in yourself**.
4. **Hymns and services:** fill in the Hymns of the Day and the upcoming services, then **Save**.
5. **Print:** click **Download the booklet** and print it on both sides (flip on the long edge), then fold it.

## Once a month

On the website, click **Settings** (at the very bottom of the page), then **Download a backup**. Keep the file somewhere other than the website: email it to yourself, or put it on a USB stick. The home page reminds you when it's been more than five weeks.

Backups are kept at: ______________________________________

## What costs money, and when

If any of these lapse, the website stops working. Make sure each one renews automatically, on a card that won't expire unnoticed, and that more than one person gets the emails about it.

| What | Where it's paid | Paid by (card/account) | Renews on | Emails go to |
|---|---|---|---|---|
| The server (Railway) | railway.com | | monthly | |
| The web address (domain) | | | once a year | |
| | | | | |

## When something goes wrong

| What you see | What to do |
|---|---|
| "Couldn't download the readings" | Try again in an hour. If it keeps happening, type the readings in yourself (the link is right there), and let a helper know. |
| The booklet has 3 pages instead of 2 | Print it anyway, and let a helper know. |
| Something looks wrong after changing Settings | On the Settings page, **Undo the last change**. |
| Forgot the password | Only someone with access to the Railway account can see or change it (below). |
| The website doesn't open at all | Check the bills above first: an unpaid server or an expired web address are the most likely causes. Then call a helper. |

**Changing the password** (needs the Railway account): open the project on railway.com, then the service, then **Variables**, and change `BULLETIN_PASSWORD`. If Railway then shows a **Deploy** button, click it. The website restarts, and everyone logs in again with the new password.

## For a helper or developer

- The program and its instructions: https://github.com/lnrssll/goarch-bulletin-builder (owner: ______________). Everything a developer needs is in `AGENTS.md` and `deploy/README.md` ("Maintenance").
- Nothing is lost when the program is moved or reinstalled, as long as there is a backup file (see "Once a month"). `deploy/README.md` explains how to put one back.
- The parish details on the back page (welcome text, the two head priests' contacts, the website) and the logo can be changed by anyone under **Settings**, without a developer.
