import datetime
import itertools
import logging
import os
import random
import re
import statistics

import django.urls as urls
import yaml
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import UserManager
from django.core.validators import FileExtensionValidator
from django.core.validators import MaxValueValidator
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Avg
from django.db.models import Exists
from django.db.models import OuterRef
from django.db.models.signals import post_save
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.utils import timezone
from django.utils.html import format_html
from django.utils.html import format_html_join
from django.utils.safestring import mark_safe
from django.utils.text import slugify
from git.exc import CommandError

import puzzle_editing.discord_integration as discord
import puzzle_editing.google_integration as google
import puzzle_editing.status as status
from puzzle_editing.git import GitRepo

logger = logging.getLogger(__name__)


class PuzzupUserManager(UserManager):
    def get_queryset(self, *args, **kwargs):
        # Prefetches the permission groups
        return super().get_queryset(*args, **kwargs).prefetch_related("groups")


class User(AbstractUser):
    class Meta:
        # make Django always use the objects manager (so that we prefetch)
        base_manager_name = "objects"

    objects = PuzzupUserManager()

    # All of these are populated by the discord sync.
    discord_username = models.CharField(max_length=500, blank=True)
    discord_nickname = models.CharField(max_length=500, blank=True)
    discord_user_id = models.CharField(max_length=500, blank=True)
    avatar_url = models.CharField(max_length=500, blank=True)

    display_name = models.CharField(
        max_length=500,
        blank=True,
        help_text="How you want your name to appear to other puzzup users.",
    )

    credits_name = models.CharField(
        max_length=80,
        help_text=(
            "How you want your name to appear in puzzle credits, e.g. " "Ben Bitdiddle"
        ),
    )
    bio = models.TextField(
        blank=True,
        help_text=(
            "Tell us about yourself. What kinds of puzzle genres or "
            "subject matter do you like?"
        ),
    )

    @property
    def is_eic(self):
        return any(g.name == "EIC" for g in self.groups.all())

    @property
    def is_editor(self):
        return any(g.name == "Editor" for g in self.groups.all())

    @property
    def is_artist(self):
        return any(g.name == "Art" for g in self.groups.all())

    @property
    def is_testsolve_coordinator(self):
        return any(g.name == "Testsolve Coordinators" for g in self.groups.all())

    @property
    def full_display_name(self):
        return "".join(
            [
                str(self),
                f" (@{self.discord_username})" if self.discord_username else "",
            ]
        ).strip()

    @property
    def hat(self):
        if self.is_eic:
            return "🎩"
        elif self.is_editor:
            return "👒"
        elif self.is_staff:
            return "🧢"
        return ""

    # Some of this templating is done in an inner loop, so doing it with
    # inclusion tags turns out to be a big performance hit. They're also small
    # enough to be pretty easy to write in Python. Separating out the versions
    # that don't even bother taking a User and just take two strings might be a
    # bit premature, but I think skipping prefetching and model construction is
    # worth it in an inner loop...
    @staticmethod
    def html_user_display_of_flat(username, display_name, linkify):
        if display_name:
            ret = format_html('<span title="{}">{}</span>', username, display_name)
        else:
            ret = username

        if linkify:
            return format_html(
                '<a href="{}">{}</a>', urls.reverse("user", args=[username]), ret
            )
        else:
            return ret

    @staticmethod
    def html_user_display_of(user, linkify):
        if not user:
            return mark_safe('<span class="empty">--</span>')
        return User.html_user_display_of_flat(user.username, str(user), linkify)

    @staticmethod
    def html_user_list_of_flat(ud_pairs, linkify):
        # iterate over ud_pairs exactly once
        s = format_html_join(
            ", ",
            "{}",
            ((User.html_user_display_of_flat(un, dn, linkify),) for un, dn in ud_pairs),
        )
        return s or mark_safe('<span class="empty">--</span>')

    @staticmethod
    def html_user_list_of(users, linkify):
        return User.html_user_list_of_flat(
            ((user.username, str(user)) for user in users),
            linkify,
        )

    @staticmethod
    def html_avatar_list_of(users, linkify):
        def fmt_user(u):
            img = "<img src='{}' width='40' height='40'/>"
            if linkify:
                url = urls.reverse("user", args=[u.username])
                return format_html('<a href="{}">' + img + "</a>", url, u.avatar_url)
            return format_html(img, u.avatar_url)

        s = format_html_join(" ", "{}", ((fmt_user(u),) for u in users))
        return s or mark_safe('<span class="empty">--</span>')

    @staticmethod
    def get_testsolve_coordinators():
        return User.objects.filter(groups__name="Testsolve Coordinators")

    def get_avatar_url_via_discord(self, discord_avatar_hash, size: int = 0) -> str:
        """Generates and returns the discord avatar url if possible
        Accepts an optional argument that defines the size of the avatar returned, between 16 and 4096 (in powers of 2),
        though this can be set when hotlinked."""

        cdn_base_url = "https://cdn.discordapp.com"

        if not self.discord_user_id:
            # we'll only "trust" information given to us by the discord API; users who haven't linked that way won't have any avatar
            return "a"

        if self.discord_username and not discord_avatar_hash:
            # This is a user with no avatar hash; accordingly, we will give them the default avatar
            try:
                discriminator = self.discord_username.split("#")[1]
            except IndexError:
                return "b"

            return f"{cdn_base_url}/embed/avatars/{discriminator}.png"

        if discord_avatar_hash and self.discord_user_id:
            if size > 0:
                size = size - (size % 2)
                size = 16 if size < 16 else size
                size = 4096 if size > 4096 else size

            return (
                f"{cdn_base_url}/avatars/{self.discord_user_id}/{discord_avatar_hash}.png"
                + (f"?size={size}" if size > 0 else "")
            )

        return "d"

    def __str__(self):
        return (
            self.display_name
            or self.credits_name
            or self.discord_username
            or self.username
        )


class Act(models.Model):
    """An act of rounds representing different stages of the hunt."""

    name = models.CharField(max_length=500)
    description = models.TextField(blank=True)

    def __str__(self):  # pylint: disable=invalid-str-returned
        return self.name


class Round(models.Model):
    """A round of answers feeding into the same metapuzzle or set of metapuzzles."""

    name = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    spoiled = models.ManyToManyField(
        User,
        blank=True,
        related_name="spoiled_rounds",
        help_text="Users spoiled on the round's answers.",
    )
    editors = models.ManyToManyField(User, related_name="editors", blank=True)
    act = models.ForeignKey(
        Act, on_delete=models.PROTECT, related_name="rounds", blank=True, null=True
    )
    puzzle_template = models.CharField(
        max_length=500,
        help_text="Path to puzzle template in the hunt repo for autopostprod",
        blank=True,
        null=True,
    )
    solution_template = models.CharField(
        max_length=500,
        help_text="Path to sol template in the hunt repo for autopostprod",
        blank=True,
        null=True,
    )

    def __str__(self):  # pylint: disable=invalid-str-returned
        return self.name


class PuzzleAnswer(models.Model):
    """An answer. Can be assigned to zero, one, or more puzzles."""

    answer = models.TextField(blank=True)
    round = models.ForeignKey(Round, on_delete=models.PROTECT, related_name="answers")
    notes = models.TextField(blank=True)
    flexible = models.BooleanField(
        default=False,
        help_text="Whether or not this answer is easy to change and satisfy meta constraints.",
    )
    case_sensitive = models.BooleanField(
        default=False,
        help_text="Whether or not this answer needs to be submitted with the correct casing.",
    )
    whitespace_sensitive = models.BooleanField(
        default=False,
        help_text="Whether or not this answer shouldn't ignore whitespaces.",
    )

    def to_json(self):
        return {
            "answer": self.answer,
            "id": self.id,
            "notes": self.notes,
            "flexible": self.flexible,
            "puzzles": self.puzzles.all(),
            "whitespace_sensitive": self.whitespace_sensitive,
        }

    def __str__(self):  # pylint: disable=invalid-str-returned
        return self.answer

    def normalize_answer(self, answer, ignore_case=True, ignore_whitespace=True):
        normalized = answer
        if ignore_whitespace:
            normalized = "".join(c for c in normalized if not c.isspace())
        if ignore_case:
            normalized = normalized.upper()

        return normalized

    def is_correct(self, guess):
        normalized_guess = self.normalize_answer(
            guess,
            ignore_case=not self.case_sensitive,
            ignore_whitespace=not self.whitespace_sensitive,
        )
        normalized_answer = self.normalize_answer(
            self.answer,
            ignore_case=not self.case_sensitive,
            ignore_whitespace=not self.whitespace_sensitive,
        )
        return normalized_answer == normalized_guess


class PuzzleTag(models.Model):
    """A tag to classify puzzles."""

    name = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    important = models.BooleanField(
        default=False,
        help_text="Important tags are displayed prominently with the puzzle title.",
    )

    def __str__(self):
        return "Tag: {}".format(self.name)


class Puzzle(models.Model):
    """A puzzle, that which Puzzup keeps track of the writing process of."""

    def generate_codename():
        with open(
            os.path.join(settings.BASE_DIR, "puzzle_editing/data/nouns-eng.txt")
        ) as f:
            nouns = [line.strip() for line in f.readlines()]
        random.shuffle(nouns)

        with open(
            os.path.join(settings.BASE_DIR, "puzzle_editing/data/adj-eng.txt")
        ) as g:
            adjs = [line.strip() for line in g.readlines()]
        random.shuffle(adjs)

        try:
            name = adjs.pop() + " " + nouns.pop()
            while Puzzle.objects.filter(codename=name).exists():
                name = adjs.pop() + " " + nouns.pop()
        except IndexError:
            return "Make up your own name!"

        return name

    name = models.CharField(max_length=500)
    codename = models.CharField(
        max_length=500,
        default=generate_codename,
        help_text="A non-spoilery name. Feel free to use the autogenerated one.",
    )

    discord_channel_id = models.CharField(
        max_length=19,
        blank=True,
    )
    discord_emoji = models.CharField(
        max_length=50,
        default=":question:",
        help_text="The emoji that'll be used in Discord notifications. Please leave in string form, e.g. :question:.",
    )

    def spoiler_free_name(self):
        if self.codename:
            return "({})".format(self.codename)
        return self.name

    def spoiler_free_title(self):
        return self.spoiler_free_name()

    @property
    def spoilery_title(self):
        name = self.name
        if self.codename:
            name += " ({})".format(self.codename)
        return name

    def important_tag_names(self):
        if hasattr(self, "prefetched_important_tag_names"):
            return self.prefetched_important_tag_names
        return [t.name for t in self.tags.all() if t.important]

    # This is done in an inner loop, so doing it with inclusion tags turns
    # out to be a big performance hit. They're also small enough to be pretty
    # easy to write in Python.
    def html_display(self):
        return format_html(
            "{}: {} {}",
            self.id,
            format_html_join(
                " ",
                "<sup>[{}]</sup>",
                ((name,) for name in self.important_tag_names()),
            ),
            self.spoiler_free_name(),
        )

    def puzzle_url(self):
        return urls.reverse("puzzle", args=[self.id])

    def html_link(self):
        return format_html(
            """<a href="{}" class="puzzle-link">{}</a>""",
            self.puzzle_url(),
            self.html_display(),
        )

    def html_link_no_tags(self):
        return format_html(
            """<a href="{}" class="puzzle-link">{}</a>""",
            self.puzzle_url(),
            self.spoiler_free_name(),
        )

    def __str__(self):
        return self.spoiler_free_title()

    authors = models.ManyToManyField(User, related_name="authored_puzzles", blank=True)
    lead_author = models.ForeignKey(
        User,
        related_name="led_puzzles",
        null=True,
        on_delete=models.PROTECT,
        help_text="The author responsible for driving the puzzle forward and getting it over the finish line.",
    )
    authors_addl = models.CharField(
        max_length=200,
        help_text="The second line of author credits. Only use in cases where a standard author credit isn't accurate.",
        blank=True,
    )

    editors = models.ManyToManyField(User, related_name="editing_puzzles", blank=True)
    needed_editors = models.IntegerField(default=2)
    spoiled = models.ManyToManyField(
        User,
        related_name="spoiled_puzzles",
        blank=True,
        help_text="Users spoiled on the puzzle.",
    )
    factcheckers = models.ManyToManyField(
        User, related_name="factchecking_puzzles", blank=True
    )
    postprodders = models.ManyToManyField(
        User, related_name="postprodding_puzzles", blank=True
    )

    # .get_status_display() is a built-in syntax that will get the human-readable text
    status = models.CharField(
        max_length=status.MAX_LENGTH,
        choices=status.DESCRIPTIONS.items(),
        default=status.INITIAL_IDEA,
    )
    status_mtime = models.DateTimeField(editable=False)

    def get_status_rank(self):
        return status.get_status_rank(self.status)

    def get_status_emoji(self):
        return status.get_emoji(self.status)

    def get_blocker(self):
        # just text describing what the category of blocker is, not a list of
        # Users or anything like that
        return status.get_blocker(self.status)

    def get_transitions(self):
        return [
            {
                "status": s,
                "status_display": status.get_display(s),
                "description": description,
            }
            for s, description in status.get_transitions(self.status, self)
        ]

    last_updated = models.DateTimeField(auto_now=True)

    summary = models.TextField(
        blank=True,
        help_text="A **non-spoilery description.** For potential testsolvers to get a sense if it'll be something they enjoy (without getting spoiled). Useful to mention: how long it'll take, how difficult it is, good for 1 solver or for a group, etc.",
    )
    description = models.TextField(
        help_text="A **spoilery description** of how the puzzle works."
    )
    editor_notes = models.TextField(
        blank=True,
        verbose_name="Mechanics",
        help_text="A **succinct list** of mechanics and themes used.",
    )
    notes = models.TextField(
        blank=True,
        help_text="Notes and requests to the editors, like for a particular answer or inclusion in a particular round.",
    )
    flavor = models.TextField(
        blank=True,
        help_text="Puzzle flavor used by creative team to motivate round art, such as 'puzzle consists of performers swallowing swords' or 'puzzle is themed as a ride through a tunnel of love'.",
    )
    flavor_approved_time = models.DateTimeField(auto_now=False, blank=True, null=True)
    answers = models.ManyToManyField(PuzzleAnswer, blank=True, related_name="puzzles")
    tags = models.ManyToManyField(PuzzleTag, blank=True, related_name="puzzles")
    priority = models.IntegerField(
        choices=(
            (1, "Very High"),
            (2, "High"),
            (3, "Medium"),
            (4, "Low"),
            (5, "Very Low"),
        ),
        default=3,
    )
    content = models.TextField(
        blank=True, help_text="The puzzle itself. An external link is fine."
    )
    solution = models.TextField(blank=True)
    is_meta = models.BooleanField(
        verbose_name="Is this a meta?", help_text="Check the box if yes.", default=False
    )
    deep = models.IntegerField(default=0)
    deep_key = models.CharField(
        max_length=500, verbose_name="DEEP key", null=True, blank=True
    )
    canonical_puzzle = models.ForeignKey(
        "self",
        help_text="If you don't know what this is for, don't worry about it.",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    # From 0-2, what is the expected difficulty of this puzzle across various fields?
    logistics_difficulty_testsolve = models.PositiveSmallIntegerField(
        validators=[MaxValueValidator(2)], blank=True, null=True
    )
    logistics_difficulty_postprod = models.PositiveSmallIntegerField(
        validators=[MaxValueValidator(2)], blank=True, null=True
    )
    logistics_difficulty_factcheck = models.PositiveSmallIntegerField(
        validators=[MaxValueValidator(2)], blank=True, null=True
    )
    # Additional logistics information
    logistics_number_testsolvers = models.CharField(max_length=512, blank=True)
    logistics_testsolve_length = models.CharField(max_length=512, blank=True)
    logistics_testsolve_skills = models.CharField(max_length=512, blank=True)

    SPECIALIZED_TYPES = [
        ("PHY", "Physical Puzzle"),
        ("EVE", "Event"),
        ("", "None of the Above"),
    ]

    logistics_specialized_type = models.CharField(
        max_length=3, choices=SPECIALIZED_TYPES, blank=True
    )

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)
        # Create a placeholder brainstorm sheet.
        # We call super().save first in order to ensure the id for this instance
        # exists.
        if is_new and google.enabled():
            google_manager = google.GoogleManager.instance()
            folder_id = google_manager.create_puzzle_folder(self)
            sheet_id = google_manager.create_brainstorm_sheet(self, folder_id)
            draft_id = google_manager.create_draft_doc(self, folder_id)
            self.solution = f"[Folder](<https://drive.google.com/drive/folders/{folder_id}>) and [Sheet](<https://docs.google.com/spreadsheets/d/{sheet_id}>)"
            self.content = (
                f"[Draft Doc](<https://docs.google.com/document/d/{draft_id}>)"
            )
            super().save(*args, **kwargs)
        elif self.status == status.NEEDS_FACTCHECK:
            if not getattr(self, "factcheck", None):
                # Create a factcheck object the first time state changes to NEEDS_FACTCHECK
                PuzzleFactcheck(puzzle=self).save()

    def get_emails(self, exclude_emails=()):
        # tcs = User.objects.filter(groups__name__in=['Testsolve Coordinators']).exclude(email="").values_list("email", flat=True)

        emails = set(self.authors.values_list("email", flat=True))
        emails |= set(self.editors.values_list("email", flat=True))
        emails |= set(self.factcheckers.values_list("email", flat=True))
        emails |= set(self.postprodders.values_list("email", flat=True))

        emails -= set(exclude_emails)
        emails -= set(("",))

        return list(emails)

    def has_postprod(self):
        try:
            return self.postprod is not None
        except PuzzlePostprod.DoesNotExist:
            return False

    def has_factcheck(self):
        try:
            return self.factcheck is not None
        except PuzzleFactcheck.DoesNotExist:
            return False

    def has_hints(self):
        return self.hints.count() > 0

    def ordered_hints(self):
        return self.hints.order_by("order")

    def has_answer(self):
        return self.answers.count() > 0

    @property
    def postprod_url(self):
        if self.has_postprod():
            return self.postprod.get_url(is_solution=False)
        return ""

    @property
    def postprod_solution_url(self):
        if self.has_postprod():
            return self.postprod.get_url(is_solution=True)
        return ""

    @property
    def author_byline(self):
        credits = [u.credits_name for u in self.authors.all()]
        credits.sort(key=lambda u: u.upper())
        if len(credits) == 2:
            return " and ".join(credits)
        else:
            return re.sub(r"([^,]+?), ([^,]+?)$", r"\1, and \2", ", ".join(credits))

    @property
    def answer(self):
        return ", ".join(self.answers.values_list("answer", flat=True)) or None

    @property
    def round(self):
        return next(iter(a.round for a in self.answers.all()), None)

    @property
    def round_name(self):
        return next(iter(a.round.name for a in self.answers.all()), None)

    @property
    def act_name(self):
        return next(
            iter(a.round.act and a.round.act.name for a in self.answers.all()), None
        )

    @property
    def metadata(self):
        editors = [u.credits_name for u in self.editors.all()]
        editors.sort(key=lambda u: u.upper())
        postprodders = [u.credits_name for u in self.postprodders.all()]
        postprodders.sort(key=lambda u: u.upper())
        return {
            "puzzle_title": self.name,
            "credits": "by %s" % self.author_byline,
            "answer": self.answer or "???",
            "round": next(iter(a.round_id for a in self.answers.all()), 1),
            "puzzle_idea_id": self.id,
            "other_credits": {
                c.credit_type: [
                    re.sub(
                        r"([^,]+?), ([^,]+?)$",
                        r"\1 and \2",
                        ", ".join([u.credits_name for u in c.users.all()]),
                    ),
                    c.text,
                ]
                for c in self.other_credits.all()
            },
            "additional_authors": self.authors_addl,
            "editors": re.sub(r"([^,]+?), ([^,]+?)$", r"\1 and \2", ", ".join(editors)),
            # "postprodders": re.sub(r"([^,]+?), ([^,]+?)$", r"\1 and \2", ", ".join(postprodders)),
            "puzzle_slug": (
                self.postprod.slug
                if self.has_postprod()
                else re.sub(
                    r'[<>#%\'"|{}\[\])(\\\^?=`;@&,]',
                    "",
                    re.sub(r"[ \/]+", "-", self.name),
                ).lower()
            ),
        }

    @property
    def slug(self):
        return slugify(self.name.lower())

    @property
    def author_list(self):
        return ", ".join(
            [
                a.credits_name if a.credits_name else a.username
                for a in self.authors.all()
            ]
        )

    @property
    def editor_list(self):
        return ", ".join(
            [
                a.credits_name if a.credits_name else a.username
                for a in self.editors.all()
            ]
        )

    def get_yaml_fixture(self):
        metadata = self.metadata
        puzzle_data = {
            "model": "puzzles.puzzle",
            "pk": self.id,
            "fields": {
                "emoji": self.discord_emoji,
                "deep": self.deep,
                # TODO: don't hardcode remaining fields
                "icon_x": 0,
                "icon_y": 0,
                "icon_size": 0,
                "text_x": 0,
                "text_y": 0,
                "testsolve_url": None,
                "unsolved_icon": "",
                "solved_icon": "",
                "points": 1,
            },
        }
        # We only try to set this via fixture if it's defined.
        if self.deep_key:
            puzzle_data["fields"]["deep_key"] = self.deep_key
        if self.canonical_puzzle:
            puzzle_data["fields"]["canonical_puzzle_id"] = self.canonical_puzzle_id

        spoilr_puzzle_data = {
            "model": "spoilr_core.puzzle",
            "pk": self.id,
            "fields": {
                "external_id": self.id,
                "round": metadata["round"],
                "answer": metadata["answer"],
                "name": self.name,
                "credits": metadata["credits"],
                "order": self.id,
                "is_meta": self.is_meta,
                "slug": metadata["puzzle_slug"],
                # TODO: don't hardcode metas
                "metas": [],
            },
        }

        hint_data = [hint.get_yaml_data() for hint in self.hints.all()]
        pseudoanswers_data = [
            pseudoanswer.get_yaml_data() for pseudoanswer in self.pseudo_answers.all()
        ]

        return yaml.dump(
            [puzzle_data, spoilr_puzzle_data, *hint_data, *pseudoanswers_data],
            sort_keys=False,
        )


class PseudoAnswer(models.Model):
    """
    Possible answers a solver might input that don't mark the puzzle as correct,
    but need handling.
    For example, they might provide a nudge for teams that are on the right
    track, or special instructions for how to obtain the correct answer.
    """

    puzzle = models.ForeignKey(
        Puzzle, on_delete=models.CASCADE, related_name="pseudo_answers"
    )
    answer = models.TextField(max_length=100)
    response = models.TextField()

    class Meta:
        unique_together = ("puzzle", "answer")
        ordering = ["puzzle", "answer"]

    def __str__(self):
        return '"%s" (%s)' % (self.puzzle.name, self.answer)

    def get_yaml_data(self):
        return {
            "model": "spoilr_core.pseudoanswer",
            "pk": self.id,
            "fields": {
                "puzzle": self.puzzle_id,
                "answer": self.answer,
                "response": self.response,
            },
        }

    def normalize(self, text):
        normalized = text
        normalized = "".join(c for c in normalized if not c.isspace())
        normalized = normalized.upper()
        return normalized

    def is_correct(self, guess):
        normalized_guess = self.normalize(guess)
        normalized_answer = self.normalize(self.answer)
        return normalized_answer == normalized_guess


class PuzzleCredit(models.Model):
    """A miscellaneous puzzle credit, such as Art"""

    ART = ("ART", "Art")
    TECH = ("TCH", "Tech")
    OTHER = ("OTH", "Other")

    puzzle = models.ForeignKey(
        Puzzle, related_name="other_credits", on_delete=models.CASCADE
    )

    users = models.ManyToManyField(User, related_name="other_credits", blank=True)

    text = models.TextField(blank=True)

    credit_type = models.CharField(
        max_length=3, choices=[ART, TECH, OTHER], default=ART
    )

    def __str__(self):
        return f"{self.get_credit_type_display()}: %s" % (
            re.sub(
                r"([^,]+?), ([^,]+?)$",
                r"\1 and \2",
                ", ".join([u.credits_name for u in self.users.all()]),
            )
            or "--"
        )

    class Meta:
        unique_together = ("puzzle", "credit_type")


@receiver(pre_save, sender=Puzzle)
def set_status_mtime(sender, instance, **_):
    try:
        obj = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        pass  # Object is new
    else:
        if obj.status != instance.status:  # Field has changed
            instance.status_mtime = timezone.now()


class SupportRequest(models.Model):
    """A request for support from one of our departments."""

    class Team(models.TextChoices):
        ART = ("ART", "🎨 Art")
        ACC = ("ACC", "🔎 Accessibility")
        TECH = ("TECH", "👩🏽‍💻 Tech")

    TEAM_TO_GROUP = {
        Team.ART: "Art Lead",
        Team.ACC: "Accessibility Lead",
        Team.TECH: "Tech Lead",
    }

    GROUP_TO_TEAM = {
        "Art Lead": Team.ART,
        "Accessibility Lead": Team.ACC,
        "Tech Lead": Team.TECH,
    }

    class Status(models.TextChoices):
        NONE = ("NO", "No need")
        REQUESTED = ("REQ", "Requested")
        APPROVED = ("APP", "Approved")
        BLOCK = ("BLOK", "Blocking")
        COMPLETE = ("COMP", "Completed")
        CANCELLED = ("X", "Cancelled")

    team = models.CharField(max_length=4, choices=Team.choices)
    puzzle = models.ForeignKey(Puzzle, on_delete=models.CASCADE)
    status = models.CharField(
        max_length=4, choices=Status.choices, default=Status.REQUESTED
    )
    team_notes = models.TextField(blank=True)
    team_notes_mtime = models.DateTimeField(auto_now=False, null=True)
    team_notes_updater = models.ForeignKey(
        User, null=True, on_delete=models.PROTECT, related_name="support_team_requests"
    )
    assignees = models.ManyToManyField(
        User,
        blank=True,
        related_name="assigned_support_requests",
    )
    author_notes = models.TextField(blank=True)
    author_notes_mtime = models.DateTimeField(auto_now=False, null=True)
    author_notes_updater = models.ForeignKey(
        User,
        null=True,
        on_delete=models.PROTECT,
        related_name="support_author_requests",
    )
    outdated = models.BooleanField(default=False)

    def get_emails(self):
        emails = {
            u.email
            for u in User.objects.filter(groups__name=self.TEAM_TO_GROUP[self.team])
            if u.email
        }
        if self.team_notes_updater and self.team_notes_updater.email:
            emails.add(self.team_notes_updater.email)

        return list(emails)

    class Meta:
        unique_together = ("puzzle", "team")


class PuzzlePostprod(models.Model):
    puzzle = models.OneToOneField(
        Puzzle, on_delete=models.CASCADE, related_name="postprod"
    )
    slug = models.CharField(
        max_length=100,
        null=False,
        blank=False,
        validators=[RegexValidator(regex=r'[^<>#%"\'|{})(\[\]\/\\\^?=`;@&, ]{1,100}')],
        help_text="The part of the URL on the hunt site referrring to this puzzle. E.g. for https://puzzle.hunt/puzzle/fifty-fifty, this would be 'fifty-fifty'.",
    )
    mtime = models.DateTimeField(auto_now=True)
    host_url = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="The base URL where this puzzle is postprodded. Defaults to staging",
    )

    def get_url(self, is_solution=False):
        act = next(iter(a.round.act_id for a in self.puzzle.answers.all()), 1)

        if self.host_url:
            host = f"{self.host_url}:8082" if act > 1 else self.host_url
        else:
            host = settings.POSTPROD_FACTORY_URL if act > 1 else settings.POSTPROD_URL
        subpath = "solutions" if is_solution else "puzzles"
        return f"{host}/{subpath}/{self.slug}"

    def __str__(self):
        return f"<Postprod {self.slug}>"


class PuzzleFactcheck(models.Model):
    """Tracks factchecking for a puzzle."""

    puzzle = models.OneToOneField(
        Puzzle, on_delete=models.CASCADE, related_name="factcheck"
    )
    google_sheet_id = models.CharField(max_length=100)
    output = models.TextField(blank=True)

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)
        # Copy the template factcheck id
        # We call super().save first in order to ensure the id for this instance
        # exists.
        if is_new and google.enabled():
            self.google_sheet_id = (
                google.GoogleManager.instance().create_factchecking_sheet(self.puzzle)
            )
            super().save(*args, **kwargs)

    def __str__(self):
        return f"<Factcheck {self.puzzle_id} {self.puzzle.spoiler_free_name()}>"


class StatusSubscription(models.Model):
    """An indication to email a user when any puzzle enters this status."""

    status = models.CharField(
        max_length=status.MAX_LENGTH,
        choices=status.DESCRIPTIONS.items(),
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    def __str__(self):
        return "{} subscription to {}".format(
            self.user, status.get_display(self.status)
        )


class PuzzleVisited(models.Model):
    """A model keeping track of when a user last visited a puzzle page."""

    puzzle = models.ForeignKey(Puzzle, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    date = models.DateTimeField(auto_now=True)


class TestsolveSession(models.Model):
    """An attempt by a group of people to testsolve a puzzle.

    Participants in the session will be able to make comments and see other
    comments in the session. People spoiled on the puzzle can also comment and
    view the participants' comments.
    """

    puzzle = models.ForeignKey(
        Puzzle, on_delete=models.CASCADE, related_name="testsolve_sessions"
    )
    started = models.DateTimeField(auto_now_add=True)
    joinable = models.BooleanField(
        default=True,
        help_text="Whether this puzzle is advertised to other users as a session they can join.",
    )
    notes = models.TextField(blank=True)

    discord_thread_id = models.CharField(
        max_length=19,
        blank=True,
    )
    google_sheets_id = models.CharField(
        max_length=64,
        blank=True,
    )

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)
        # Create a thread in Discord and a Google Sheets for new testsolve sessions.
        # We call super().save first in order to ensure the id for this instance
        # exists.
        if is_new:
            discord_thread_id, google_sheets_id = create_testsolve_thread(self)
            self.discord_thread_id = discord_thread_id
            self.google_sheets_id = google_sheets_id
            super().save(*args, **kwargs)

    @property
    def time_since_started(self):
        td = datetime.datetime.now(tz=datetime.timezone.utc) - self.started
        minutes = td.seconds / 60
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)
        return " ".join(
            [
                time
                for time in [
                    f"{int(days)}d" if days > 0 else None,
                    f"{int(hours):02}h" if hours > 0 else None,
                    f"{int(minutes):02}m" if minutes > 0 else None,
                ]
                if time
            ]
        )

    def participants(self):
        users = []
        for p in self.participations.all():
            p.user.current = p.ended is None
            users.append(p.user)
        return users

    def active_participants(self):
        return [p.user for p in self.participations.all() if p.ended is None]

    def get_done_participants_display(self):
        participations = list(self.participations.all())
        done_participations = [p for p in participations if p.ended is not None]
        return "{} / {}".format(len(done_participations), len(participations))

    def has_correct_guess(self):
        return any(g.correct for g in self.guesses.all())

    def get_average_fun(self):
        try:
            return statistics.mean(
                p.fun_rating
                for p in self.participations.all()
                if p.fun_rating is not None
            )
        except statistics.StatisticsError:
            return None

    def get_average_diff(self):
        try:
            return statistics.mean(
                p.difficulty_rating
                for p in self.participations.all()
                if p.difficulty_rating is not None
            )
        except statistics.StatisticsError:
            return None

    def get_average_hours(self):
        try:
            return statistics.mean(
                p.hours_spent
                for p in self.participations.all()
                if p.hours_spent is not None
            )
        except statistics.StatisticsError:
            return None

    def get_emails(self, exclude_emails=()):
        emails = set(self.puzzle.get_emails())
        emails |= set(p.email for p in self.participants() if p.email is not None)

        emails -= set(exclude_emails)
        emails -= set(("",))

        return list(emails)

    def __str__(self):
        return "Testsolve session #{} on {}".format(self.id, self.puzzle)


def create_testsolve_thread(instance: TestsolveSession):
    if discord.enabled():
        try:
            puzzle = instance.puzzle
            c = discord.get_client()

            # Create a temporary message, start the thread from that message, and then delete the message.
            # This creates a pseudo-private thread.
            message = c.post_message(
                settings.DISCORD_TESTSOLVE_CHANNEL_ID,
                f"Temp message for testsolve session {instance.id}.",
            )
            thread = discord.build_testsolve_thread(instance, c.guild_id)
            thread = c.save_thread(thread, message["id"])
            c.delete_message(settings.DISCORD_TESTSOLVE_CHANNEL_ID, message["id"])

            author_tags = discord.get_tags(puzzle.authors.all(), False)
            editor_tags = discord.get_tags(puzzle.editors.all(), False)
            c.post_message(
                thread.id,
                f"New testsolve session created for {puzzle.name}.\n"
                # This is a hack to auto-add authors and editors to the thread
                # by tagging them (to get around Discord rate limits).
                f"Author(s): {', '.join(author_tags)}\n"
                f"Editor(s): {', '.join(editor_tags)}",
            )

            sheet_id = google.GoogleManager.instance().create_testsolving_sheet(
                instance
            )
            message = c.post_message(
                thread.id,
                f"Google Sheets link: https://docs.google.com/spreadsheets/d/{sheet_id}",
            )
            c.pin_message(thread.id, message["id"])

            TestsolveSession.objects.filter(id=instance.id).update(
                discord_thread_id=thread.id, google_sheets_id=sheet_id
            )

            return (thread.id, sheet_id)
        except Exception:
            logger.exception("Failed to create Discord thread or Google sheets.")
    return ("", "")


class PuzzleComment(models.Model):
    """A comment on a puzzle.

    All comments on a puzzle are visible to people spoiled on the puzzle.
    Comments may or may not be associated with a testsolve session; if they
    are, they will also be visible to people participating in or viewing the
    session."""

    puzzle = models.ForeignKey(
        Puzzle, on_delete=models.CASCADE, related_name="comments"
    )
    author = models.ForeignKey(User, on_delete=models.PROTECT, related_name="comments")
    date = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)
    is_system = models.BooleanField()
    is_feedback = models.BooleanField(
        help_text="Whether or not this comment is created as feedback from a testsolve session"
    )
    testsolve_session = models.ForeignKey(
        TestsolveSession,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="comments",
    )
    content = models.TextField(
        blank=True,
        help_text="The content of the comment. Should probably only be blank if the status_change is set.",
    )
    status_change = models.CharField(
        max_length=status.MAX_LENGTH,
        choices=status.DESCRIPTIONS.items(),
        blank=True,
        help_text="Any status change caused by this comment. Only used for recording history and computing statistics; not a source of truth (i.e. the puzzle will still store its current status, and this field's value on any comment doesn't directly imply anything about that in any technically enforced way).",
    )

    def __str__(self):
        return "Comment #{} on {}".format(self.id, self.puzzle)


class CommentReaction(models.Model):
    # Since these are frivolous and display-only, I'm not going to bother
    # restricting them on the database model layer.
    EMOJI_OPTIONS = ["👍", "👎", "🎉", "❤️", "😄", "🤔", "😕", "❓", "👀", "🍖"]
    emoji = models.CharField(max_length=8)
    comment = models.ForeignKey(
        PuzzleComment, on_delete=models.CASCADE, related_name="reactions"
    )
    reactor = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="reactions"
    )

    def __str__(self):
        return "{} reacted {} on {}".format(
            self.reactor.username, self.emoji, self.comment
        )

    class Meta:
        unique_together = ("emoji", "comment", "reactor")

    @classmethod
    def toggle(cls, emoji, comment, reactor):
        # This just lets you react with any string to a comment, but it's
        # not the end of the world.
        my_reactions = cls.objects.filter(comment=comment, emoji=emoji, reactor=reactor)
        # Force the queryset instead of checking if it's empty because, if
        # it's not empty, we care about its contents.
        if len(my_reactions) > 0:
            my_reactions.delete()
        else:
            cls(emoji=emoji, comment=comment, reactor=reactor).save()


class TestsolveParticipation(models.Model):
    """Represents one user's participation in a testsolve session.

    Used to record the user's start and end time, as well as ratings on the
    testsolve."""

    session = models.ForeignKey(
        TestsolveSession, on_delete=models.CASCADE, related_name="participations"
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="testsolve_participations"
    )
    started = models.DateTimeField(auto_now_add=True)
    ended = models.DateTimeField(null=True, blank=True)
    fun_rating = models.IntegerField(null=True, blank=True)
    difficulty_rating = models.IntegerField(null=True, blank=True)
    hours_spent = models.FloatField(
        null=True,
        help_text="**Hours spent**. Your best estimate of how many hours you spent on this puzzle. Decimal numbers are allowed.",
    )

    general_feedback = models.TextField(
        null=True,
        blank=True,
        help_text="What did you like & dislike about this puzzle? Is there anything you think should be changed (e.g. amount of flavor/cluing, errata, tech issues, mechanics, theming, etc.)?",
    )

    misc_feedback = models.TextField(
        null=True,
        blank=True,
        help_text="Anything else you want to add? If you were spoiled, mention it here. (This can include: things you tried, any shortcuts you found, break-ins, stuck points, accessibility)",
    )

    clues_needed = models.TextField(
        null=True,
        blank=True,
        help_text="Did you solve the complete puzzle before getting the answer, or did you shortcut, and if so, how much remained unsolved?",
    )

    aspects_enjoyable = models.TextField(
        null=True,
        blank=True,
        help_text="What parts of the puzzle were particularly enjoyable, if any?",
    )
    aspects_unenjoyable = models.TextField(
        null=True,
        blank=True,
        help_text="What parts of the puzzle were not enjoyable, if any?",
    )
    aspects_accessibility = models.TextField(
        null=True,
        blank=True,
        help_text="If you have physical issues such as a hearing impairment, vestibular disorder, etc., what problems did you encounter with this puzzle, if any?",
    )

    technical_issues = models.BooleanField(
        default=False,
        null=False,
        help_text="Did you encounter any technical problems with any aspect of the puzzle, including problems with your browser, any assistive device, etc. as well as any puzzle-specific tech?",
    )
    technical_issues_device = models.TextField(
        null=True,
        blank=True,
        help_text="**If Yes:** What type of device was the issue associated with? Please be as specific as possible (PC vs Mac, what browser, etc",
    )
    technical_issues_description = models.TextField(
        null=True, blank=True, help_text="**If Yes:** Please describe the issue"
    )

    instructions_overall = models.BooleanField(
        default=True, null=True, help_text="Were the instructions clear?"
    )
    instructions_feedback = models.TextField(
        null=True,
        blank=True,
        help_text="**If No:** What was confusing about the instructions?",
    )

    FLAVORTEXT_CHOICES = [
        ("helpful", "It was helpful and appropriate"),
        ("too_leading", "It was too leading"),
        ("not_helpful", "It was not helpful"),
        ("confused", "It confused us, or led us in a wrong direction"),
        ("none_but_ok", "There was no flavor text, and that was fine"),
        ("none_not_ok", "There was no flavor text, and I would have liked some"),
    ]

    flavortext_overall = models.CharField(
        max_length=20,
        null=True,
        help_text="Which best describes the flavor text?",
        choices=FLAVORTEXT_CHOICES,
    )
    flavortext_feedback = models.TextField(
        null=True, blank=True, help_text="**If Helpful:** How did the flavor text help?"
    )

    stuck_overall = models.BooleanField(
        default=False,
        null=False,
        help_text="**Were you stuck at any point?** E.g. not sure how to start, not sure which data to gather, etc.",
    )
    stuck_points = models.TextField(
        null=True,
        blank=True,
        help_text="**If Yes:** Where did you get stuck? List as many places as relevant.",
    )
    stuck_time = models.FloatField(
        null=True,
        blank=True,
        help_text="**If Yes:** For about how long were you stuck?",
    )
    stuck_unstuck = models.TextField(
        null=True,
        blank=True,
        help_text="**If Yes:** What helped you get unstuck? Was it a satisfying aha?",
    )

    errors_found = models.TextField(
        null=True,
        blank=True,
        help_text="What errors, if any, did you notice in the puzzle?",
    )

    suggestions_change = models.TextField(
        null=True,
        blank=True,
        help_text="Do you have suggestions to change the puzzle? Please explain why your suggestion(s) will help.",
    )

    suggestions_keep = models.TextField(
        null=True,
        blank=True,
        help_text="Do you have suggestions for things that should definitely stay in the puzzle? Please explain what you like about them.",
    )

    def __str__(self):
        return "Testsolve participation: {} in Session #{}".format(
            self.user.username, self.session.id
        )


@receiver(post_save, sender=TestsolveParticipation)
def add_testsolver_to_thread(
    sender, instance: TestsolveParticipation, created: bool, **kwargs
):
    if not created:
        return
    if discord.enabled():
        session = instance.session
        c = discord.get_client()
        thread = discord.get_thread(c, session)
        if not thread:
            return
        for did in discord.get_dids([instance.user]):
            if did:
                c.add_member_to_thread(thread.id, did)


class TestsolveGuess(models.Model):
    """A guess made by a user in a testsolve session."""

    class Meta:
        verbose_name_plural = "testsolve guesses"

    session = models.ForeignKey(
        TestsolveSession, on_delete=models.CASCADE, related_name="guesses"
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="guesses")
    guess = models.TextField(max_length=500, blank=True)
    correct = models.BooleanField()
    partially_correct = models.BooleanField(default=False)
    partial_response = models.TextField(blank=True)
    date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        correct_text = "Correct" if self.correct else "Incorrect"
        return "{}: {} guess by {} in Session #{}".format(
            self.guess, correct_text, self.user.username, self.session.id
        )


def is_spoiled_on(user, puzzle):
    # should use prefetch_related("spoiled") when using this
    return user in puzzle.spoiled.all()


def is_author_on(user, puzzle):
    return user in puzzle.authors.all()


def is_editor_on(user, puzzle):
    return user in puzzle.editors.all()


def is_factchecker_on(user, puzzle):
    return user in puzzle.factcheckers.all()


def is_postprodder_on(user, puzzle):
    return user in puzzle.postprodders.all()


def get_user_role(user, puzzle):
    if is_author_on(user, puzzle):
        return "author"
    elif is_editor_on(user, puzzle):
        return "editor"
    elif is_postprodder_on(user, puzzle):
        return "postprodder"
    elif is_factchecker_on(user, puzzle):
        return "factchecker"
    else:
        return None


class Hint(models.Model):
    class Meta:
        unique_together = ("puzzle", "description")
        ordering = ["order"]

    puzzle = models.ForeignKey(Puzzle, on_delete=models.PROTECT, related_name="hints")
    order = models.FloatField(
        blank=False,
        null=False,
        help_text="Order in the puzzle - use 0 for a hint at the very beginning of the puzzle, or 100 for a hint on extraction, and then do your best to extrapolate in between. Decimals are okay. For multiple subpuzzles, assign a whole number to each subpuzzle and use decimals off of that whole number for multiple hints in the subpuzzle.",
    )
    description = models.CharField(
        max_length=1000,
        blank=False,
        null=False,
        help_text='A description of when this hint should apply; e.g. "The solvers have not yet figured out that the mirrors represent word transformations"',
    )
    keywords = models.CharField(
        max_length=100,
        blank=True,
        null=False,
        help_text="Comma-separated keywords to look for in hunters' hint requests before displaying this hint suggestion",
    )
    content = models.CharField(
        max_length=1000,
        blank=False,
        null=False,
        help_text="Canned hint to give a team (can be edited by us before giving it)",
    )

    def get_keywords(self):
        return self.keywords.split(",")

    def __str__(self):
        return f"Hint #{self.order} for {self.puzzle}"

    def get_yaml_data(self):
        return {
            "model": "spoilr_hints.cannedhint",
            "pk": self.id,
            "fields": {
                "puzzle": self.puzzle_id,
                "description": self.description,
                "order": self.order,
                "keywords": self.keywords,
                "content": self.content,
            },
        }


class SiteSetting(models.Model):
    """Arbitrary settings we don't want to customize from code."""

    key = models.CharField(max_length=100, unique=True)
    value = models.TextField()

    def __str__(self):
        return "{} = {}".format(self.key, self.value)

    @classmethod
    def get_setting(cls, key):
        try:
            return cls.objects.get(key=key).value
        except cls.DoesNotExist:
            return None

    @classmethod
    def get_int_setting(cls, key):
        try:
            return int(cls.objects.get(key=key).value)
        except cls.DoesNotExist:
            return None
        except ValueError:
            return None
