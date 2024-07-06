import re
import urllib.parse

from asgiref.sync import async_to_sync
from bs4 import BeautifulSoup
from django.conf import settings
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def enabled():
    """Returns true if the django settings enable discord."""
    return "credentials" in settings.DRIVE_SETTINGS


class GoogleManager:
    __instance = None

    @classmethod
    def instance(cls):
        """
        Get a single instance per process.
        """
        if cls.__instance is None:
            cls.__instance = cls()
        return cls.__instance

    def __init__(self):
        self.creds = service_account.Credentials.from_service_account_info(
            settings.DRIVE_SETTINGS["credentials"],
            scopes=SCOPES,
        )
        drive_service = build("drive", "v3", credentials=self.creds)
        self.files = drive_service.files()
        self.permissions = drive_service.permissions()
        self.spreadsheets = build("sheets", "v4", credentials=self.creds).spreadsheets()

    def move_to_folder(self, file_id, folder_id):
        # file_id is allowed to be a folder
        existing_parents = ",".join(
            self.files.get(fileId=file_id, fields="parents").execute()["parents"]
        )
        self.files.update(
            body={},
            fileId=file_id,
            addParents=folder_id,
            removeParents=existing_parents,
        ).execute()

    def create_brainstorm_sheet(self, puzzle):
        # Create a child folder in the puzzle draft folder
        file_metadata = {
            "name": puzzle.spoiler_free_title(),
            "mimeType": "application/vnd.google-apps.folder",
        }
        folder_id = (
            self.files.create(body=file_metadata, fields="id").execute().get("id")
        )
        self.move_to_folder(folder_id, settings.PUZZLE_DRAFT_FOLDER_ID)
        self.transfer_ownership(folder_id)
        return self._create_sheet(
            title=f"{puzzle.spoiler_free_title()} Brainstorm",
            text="Puzzup Link",
            url=f"{settings.PUZZUP_URL}/puzzle/{puzzle.id}",
            folder_id=folder_id,
        )

    def create_testsolving_sheet(self, session):
        return self._create_sheet(
            title=f"{session.puzzle.name} (Testsolve #{session.id})",
            text="Puzzup Testsolve Session",
            url=f"{settings.PUZZUP_URL}/testsolve/{session.id}",
            folder_id=settings.TESTSOLVING_FOLDER_ID,
            template_id=settings.TESTSOLVING_TEMPLATE_ID,
        )

    def create_factchecking_sheet(self, puzzle):
        # Look up the existing puzzle folder, if any
        file_name = puzzle.spoiler_free_title()
        template_id = (
            self.files.copy(
                fileId=settings.FACTCHECKING_TEMPLATE_ID,
                fields="id",
                body={"name": f"{puzzle.id} {file_name} Factcheck"},
            )
            .execute()
            .get("id")
        )
        self.move_to_folder(template_id, settings.FACTCHECKING_FOLDER_ID)
        self.transfer_ownership(template_id)
        return template_id

    def transfer_ownership(self, file_id):
        file = self.files.get(fileId=file_id, fields="id,permissions").execute()
        permission = next(
            p for p in file["permissions"] if p["emailAddress"] == settings.SERVER_EMAIL
        )
        self.permissions.update(
            fileId=file["id"],
            permissionId=permission["id"],
            body={"role": "writer", "pendingOwner": "true"},
        ).execute()

    def _create_sheet(self, title, text, url, folder_id, template_id=None):
        """Creates spreadsheet where top-left cell is text that goes to given URL."""
        if template_id:
            spreadsheet_id = (
                self.files.copy(
                    fileId=template_id,
                    fields="id",
                    body={"name": title},
                )
                .execute()
                .get("id")
            )

        else:
            spreadsheet_id = (
                self.spreadsheets.create(
                    body={
                        "properties": {
                            "title": title,
                        },
                    },
                    fields="spreadsheetId",
                )
                .execute()
                .get("spreadsheetId")
            )

        req_body = {
            "values": [
                [f'=HYPERLINK("{url}", "{text}")'],
            ]
        }
        self.spreadsheets.values().update(
            spreadsheetId=spreadsheet_id,
            range="A1:B2",
            valueInputOption="USER_ENTERED",
            body=req_body,
        ).execute()

        self.move_to_folder(spreadsheet_id, folder_id)
        self.transfer_ownership(spreadsheet_id)
        return spreadsheet_id

    def get_gdoc_html(self, file_id):
        html = self.files.export(fileId=file_id, mimeType="text/html").execute()
        return self.clean_html(html)

    def clean_html(self, html):
        """Cleans up some garbage exported from Google Docs using beautiful soup."""
        cleaner = HtmlCleaner(html)
        cleaner.clean()
        cleaner.map_to_react()
        return cleaner.to_string()


class HtmlCleaner:
    def __init__(self, html):
        self.soup = BeautifulSoup(html, "html.parser")

    def map_to_react(self):
        # Attributes mapped from html to React
        MAPPED_ATTRS = {"colspan": "colSpan", "rowspan": "rowSpan"}
        # Tag names mapped from html to React
        MAPPED_TAGS = {"table": "Table", "img": "SheetableImage"}

        for attr in MAPPED_ATTRS.keys():
            for tag in self.soup.find_all(attrs={attr: True}):
                tag[MAPPED_ATTRS[attr]] = tag[attr]
                del tag[attr]

        # Swap some tags for the React component version.
        for tag in self.soup.find_all(MAPPED_TAGS.keys()):
            tag.name = MAPPED_TAGS[tag.name]

    def clean_google_urls(self, url: str):
        # For some reason Google is adding redirects to all urls, fix this with regex
        match = re.search(r"^https:\/\/www\.google\.com\/url\?q=(.*?)&", url)
        if match:
            return urllib.parse.unquote(match.group(1), encoding="utf-8")
        return url

    def clean_tables(self):
        # Wrap <table> in <thead> and <tbody>
        for tag in self.soup.find_all("table"):
            if not tag.contents:
                continue

            # Add thead if the first row contains a bold tag
            first_row = tag.contents[0]
            has_header = bool(first_row.find("b"))
            if has_header:
                thead = self.soup.new_tag("thead")
                thead.append(first_row.extract())
                # Remove bold in thead, since th is bold by default
                for b_tag in thead.find_all("b"):
                    b_tag.unwrap()
                # Swap td for th
                for td_tag in thead.find_all("td"):
                    td_tag.name = "th"
                tag.insert(0, thead)

            tbody = self.soup.new_tag("tbody")
            for content in reversed(tag.contents[1:] if has_header else tag.contents):
                tbody.insert(0, content.extract())
            tag.append(tbody)

        # Remove extra paragraphs inside td/th
        for tag in self.soup.find_all("p"):
            if tag.parent and tag.parent.name in ("td", "th"):
                tag.unwrap()

    def clean(self):
        # Tuple of tags that are allowed to be empty
        ALLOWED_EMPTY_TAGS = ("img",)

        # Nuke the whole head section, including stylesheet and meta tags
        self.soup.head.decompose()

        # Convert bold, italics, and underline styles
        def has_style(search_list):
            return lambda style: any(
                (search in (style or "")) for search in search_list
            )

        styles = {
            "i": ["font-style:italic"],
            "b": ["font-weight:700"],
            "u": ["text-decoration:underline"],
            "Monospace": [
                'font-family:"Consolas"',
                'font-family:"Roboto Mono"',
                'font-family:"Courier New"',
            ],
        }
        for tag_name, style_list in styles.items():
            for tag in self.soup.find_all(style=has_style(style_list)):
                if tag_name == "u" and tag.find("a", recursive=False):
                    # Google Docs wraps links with an extra underline span, ignore those
                    tag.unwrap()
                    continue
                tag.wrap(self.soup.new_tag(tag_name))

        # Remove almost all extraneous html attributes
        for attr in ("id", "class", "style", "start"):
            for tag in self.soup.find_all(attrs={attr: True}):
                del tag[attr]

        # Remove colspan/rowspan = 1
        for attr in ("colspan", "rowspan"):
            for tag in self.soup.find_all(attrs={attr: "1"}):
                del tag[attr]

        # Remove all of the spans, as well as the outer html and body
        for tag in self.soup.find_all(["span", "body", "html"]):
            tag.unwrap()

        # Clean up a tags href
        for tag in self.soup.find_all("a", href=True):
            tag["href"] = self.clean_google_urls(tag["href"])

        self.clean_tables()

        for tag in self.soup.find_all(lambda tag: not tag.contents):
            if tag.name == "p":
                # Clean up empty paragraphs
                tag.decompose()
            elif tag.name not in ALLOWED_EMPTY_TAGS:
                # Remove other empty tags
                tag.unwrap()

        # Delete any extra line breaks at the end of the doc.
        for tag in reversed(self.soup.contents):
            if tag.name == "br":
                tag.decompose()
            else:
                break

    def to_string(self):
        return str(self.soup)
