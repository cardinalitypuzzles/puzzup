import typing as t
from enum import Flag
from itertools import chain

from pydantic import BaseModel
from pydantic import Field

# A PermLike is anything we can convert into a Permission.
PermLike = t.Union["Permission", str, int, None]


class Permission(Flag):
    """Represents a discord permission.

    Use .of to coerce any PermLike to a Permission:

    >>> # Same as Permission(0)
    >>> Permission.of(None)
    <Permission.NO_PERMISSION: 0>
    >>> # Same as Permission(1)
    >>> Permission.of(1)
    <Permission.CREATE_INSTANT_INVITE: 1>
    >>> # Same as Permission(1)
    >>> Permission.of("1")
    <Permission.CREATE_INSTANT_INVITE: 1>
    >>> # Same as Permission["CONNECT"]
    >>> Permission.of("CONNECT")
    <Permission.CONNECT: 1048576>
    >>> # Passes through the permission
    >>> Permission.of(Permission.SEND_MESSAGES)
    <Permission.SEND_MESSAGES: 2048>

    Permissions support bitwise operations and containment checks:

    >>> p = Permission.KICK_MEMBERS | Permission(9)
    >>> p
    <Permission.ADMINISTRATOR|KICK_MEMBERS|CREATE_INSTANT_INVITE: 11>
    >>> (Permission.KICK_MEMBERS | Permission.BAN_MEMBERS) in Permission(1023)
    True
    """

    # https://discord.com/developers/docs/topics/permissions#permissions-bitwise-permission-flags
    NO_PERMISSION = 0
    CREATE_INSTANT_INVITE = (1 << 0)
    KICK_MEMBERS = (1 << 1)
    BAN_MEMBERS = (1 << 2)
    ADMINISTRATOR = (1 << 3)
    MANAGE_CHANNELS = (1 << 4)
    MANAGE_GUILD = (1 << 5)
    ADD_REACTIONS = (1 << 6)
    VIEW_AUDIT_LOG = (1 << 7)
    PRIORITY_SPEAKER = (1 << 8)
    STREAM = (1 << 9)
    VIEW_CHANNEL = (1 << 10)
    SEND_MESSAGES = (1 << 11)
    SEND_TTS_MESSAGES = (1 << 12)
    MANAGE_MESSAGES = (1 << 13)
    EMBED_LINKS = (1 << 14)
    ATTACH_FILES = (1 << 15)
    READ_MESSAGE_HISTORY = (1 << 16)
    MENTION_EVERYONE = (1 << 17)
    USE_EXTERNAL_EMOJIS = (1 << 18)
    VIEW_GUILD_INSIGHTS = (1 << 19)
    CONNECT = (1 << 20)
    SPEAK = (1 << 21)
    MUTE_MEMBERS = (1 << 22)
    DEAFEN_MEMBERS = (1 << 23)
    MOVE_MEMBERS = (1 << 24)
    USE_VAD = (1 << 25)
    CHANGE_NICKNAME = (1 << 26)
    MANAGE_NICKNAMES = (1 << 27)
    MANAGE_ROLES = (1 << 28)
    MANAGE_WEBHOOKS = (1 << 29)
    MANAGE_GUILD_EXPRESSIONS = (1 << 30)
    USE_APPLICATION_COMMANDS = (1 << 31)
    REQUEST_TO_SPEAK = (1 << 32)
    MANAGE_EVENTS = (1 << 33)
    MANAGE_THREADS = (1 << 34)
    CREATE_PUBLIC_THREADS = (1 << 35)
    CREATE_PRIVATE_THREADS = (1 << 36)
    USE_EXTERNAL_STICKERS = (1 << 37)
    SEND_MESSAGES_IN_THREADS = (1 << 38)
    USE_EMBEDDED_ACTIVITIES = (1 << 39)
    MODERATE_MEMBERS = (1 << 40)
    VIEW_CREATOR_MONETIZATION_ANALYTICS = (1 << 41)
    USE_SOUNDBOARD = (1 << 42)
    CREATE_GUILD_EXPRESSIONS = (1 << 43)
    CREATE_EVENTS = (1 << 44)
    USE_EXTERNAL_SOUNDS = (1 << 45)
    SEND_VOICE_MESSAGES = (1 << 46)
    SEND_POLLS = (1 << 49)
    USE_EXTERNAL_APPS = (1 << 50)

    @classmethod
    def __get_validators__(cls):
        yield cls.of

    @classmethod
    def of(cls, obj: PermLike) -> "Permission":
        """Coerce an object to a permission."""
        if obj is None:
            return Permission(0)
        if isinstance(obj, str):
            try:
                return Permission(int(obj))
            except ValueError:
                return Permission[obj]
        return Permission(obj)


class Overwrite(BaseModel):
    """A Discord permission overwrite.

    It's a pydantic model, so it has a lot of smart helpers, e.g.:

    >>> o1 = Overwrite.parse_obj(dict(
    ...     id="foo", type=1, allow="2097664", deny="4"))
    >>> o1.describe()
    'User foo can SPEAK|STREAM; cannot BAN_MEMBERS.'
    >>> o1.dict()
    {'id': 'foo', 'type': 1, 'allow': '2097664', 'deny': '4'}
    """

    id: str
    type: int
    allow: Permission = Permission.NO_PERMISSION
    deny: Permission = Permission.NO_PERMISSION

    class Config:
        frozen = True

    def is_empty(self):
        """True if our permissions are empty."""
        return not self.allow and not self.deny

    def __nonzero__(self):
        return self.is_empty()

    def describe(self) -> str:
        label = f"User {self.id}" if self.type else f"Role {self.id}"
        astr = str(self.allow)[11:]  # strip leading Permission.
        dstr = str(self.deny)[11:]  # strip leading Permission.
        if not self.allow and not self.deny:
            return f"{label} has no overwrites."
        if not self.deny:
            return f"{label} can {astr}."
        if not self.allow:
            return f"{label} cannot {dstr}."
        return f"{label} can {astr}; cannot {dstr}."

    def dict(self, *a, **kw):
        """Like pydantic's dict, but allow and deny become strings.

        This is necessary for discord.

        >>> o1 = Overwrite(id="foo", type=1, allow=3, deny=4)
        >>> o1.dict()
        {'id': 'foo', 'type': 1, 'allow': '3', 'deny': '4'}
        """
        d = super().dict(*a, **kw)
        for k in ["allow", "deny"]:
            if k in d:
                d[k] = str(d[k].value)
        return d

    def update(
        self, allow: PermLike = None, deny: PermLike = None, ignore: PermLike = None
    ) -> "Overwrite":
        """Return an identical Overwrite but with permissions changed.

        Bits in allow will be enabled in self.allow and disabled in self.deny.
        Bits in deny will be enabled in self.deny and disabled in self.allow.
        Bits in ignore will be disabled in both.

        Raises a ValueError if the sets overlap.

        >>> o = Overwrite(id="foo", type=1)
        >>> o.describe()
        'User foo has no overwrites.'
        >>> vstream = Permission.STREAM | Permission.USE_VAD
        >>> o2 = o.update(allow=Permission.VIEW_CHANNEL, deny=vstream)
        >>> o2.describe()
        'User foo can VIEW_CHANNEL; cannot USE_VAD|STREAM.'
        >>> o3 = o2.update(ignore=Permission.STREAM, allow=Permission.SPEAK)
        >>> o3.describe()
        'User foo can SPEAK|VIEW_CHANNEL; cannot USE_VAD.'
        >>> o.update(allow=Permission.STREAM, ignore=Permission.STREAM)
        Traceback (most recent call last):
            ...
        ValueError: Contradiction: allow Permission.STREAM, deny Permission.NO_PERMISSION, ignore Permission.STREAM
        """
        allow = Permission.of(allow)
        deny = Permission.of(deny)
        ignore = Permission.of(ignore)
        if allow & deny or allow & ignore or deny & ignore:
            raise ValueError(
                f"Contradiction: allow {allow}, deny {deny}, ignore {ignore}"
            )
        return Overwrite(
            id=self.id,
            type=self.type,
            allow=(self.allow | allow) & ~deny & ~ignore,
            deny=(self.deny | deny) & ~allow & ~ignore,
        )


class Overwrites(BaseModel):
    """Models a set of user and role overwrites.

    It can parse the overwrite lists exposed by discord's API:
    >>> o = Overwrites.from_discord([
    ...     dict(id='foo', type=1, allow="3"),
    ...     dict(id='bar', type=0, deny="1"),
    ...     dict(id='baz', type=1, allow="1", deny=2),
    ... ])
    >>> o.users['foo'].describe()
    'User foo can KICK_MEMBERS|CREATE_INSTANT_INVITE.'
    >>> o.roles['bar'].describe()
    'Role bar cannot CREATE_INSTANT_INVITE.'
    >>> o.to_discord() == [
    ...     {'id': 'foo', 'type': 1, 'allow': '3', 'deny': '0'},
    ...     {'id': 'baz', 'type': 1, 'allow': '1', 'deny': '2'},
    ...     {'id': 'bar', 'type': 0, 'allow': '0', 'deny': '1'}]
    True

    The 'set' helper adds an Overwrite, adding it to the right type
    automatically:

    >>> o.set(Overwrite(id='new', type=0, allow=2))
    >>> o.roles['new'].describe()
    'Role new can KICK_MEMBERS.'

    It will replace any existing overwrite with that name, complaining if this
    changes the type:

    >>> o.set(Overwrite(id='new', type=0, allow=1))
    >>> o.roles['new'].describe()
    'Role new can CREATE_INSTANT_INVITE.'
    >>> o.set(Overwrite(id='new', type=1, allow=1))
    Traceback (most recent call last):
        ...
    ValueError: Id new is a role, not a user.

    Note that setting an empty overwrite will clear it:

    >>> 'new' in o.roles
    True
    >>> o.set(o.get_role('new').update(ignore="CREATE_INSTANT_INVITE"))
    >>> 'new' in o.roles
    False
    """

    users: dict[str, Overwrite] = Field(default_factory=dict)
    roles: dict[str, Overwrite] = Field(default_factory=dict)

    @classmethod
    def from_seq(cls, overwrites: t.Sequence[Overwrite] = ()) -> "Overwrites":
        obj = cls()
        for o in overwrites:
            obj.set(o)
        return obj

    @classmethod
    def from_discord(cls, json: list[dict]) -> "Overwrites":
        overwrites = [Overwrite.parse_obj(item) for item in json]
        return cls.from_seq(overwrites)

    def all_overwrites(self):
        return chain(self.users.values(), self.roles.values())

    def __iter__(self):
        yield from self.all_overwrites()

    def to_discord(self, *a, **kw) -> list[dict]:
        return [o.dict(*a, **kw) for o in self.all_overwrites() if not o.is_empty()]

    def dict(self, *a, **kw):
        return self.to_discord(*a, **kw)

    def parse_obj(self, obj):
        return self.from_discord(obj)

    def get_user(self, uid):
        """Get a user's overwrite, or a default one if none exists"""
        if uid in self.roles:
            raise ValueError(f"Id {uid} is a role, not a user.")
        return self.users.get(uid, Overwrite(id=uid, type=1))

    def get_role(self, rid):
        """Get a role's overwrite, or a default one if none exists"""
        if rid in self.users:
            raise ValueError(f"Id {rid} is a user, not a role.")
        return self.roles.get(rid, Overwrite(id=rid, type=0))

    def user_ids(self) -> list[str]:
        return list(self.users)

    def role_ids(self) -> list[str]:
        return list(self.roles)

    def set(self, overwrite: Overwrite):
        if overwrite.type == 0:
            main = self.roles
            other = self.users
        else:
            other = self.roles
            main = self.users
        if overwrite.id in other:
            if other is self.users:
                want, got = "role", "user"
            else:
                want, got = "user", "role"
            raise ValueError(f"Id {overwrite.id} is a {got}, not a {want}.")
        if overwrite.is_empty():
            if overwrite.id in main:
                del main[overwrite.id]
        else:
            main[overwrite.id] = overwrite

    def update_user(
        self,
        uid: str,
        allow: PermLike = None,
        deny: PermLike = None,
        ignore: PermLike = None,
    ):
        """
        >>> os = Overwrites()
        >>> os.update_user("foo", allow=Permission.VIEW_CHANNEL)
        >>> os.get_user("foo").describe()
        'User foo can VIEW_CHANNEL.'
        >>> os.update_user("foo", deny=Permission.VIEW_CHANNEL)
        >>> os.get_user("foo").describe()
        'User foo cannot VIEW_CHANNEL.'
        >>> os.update_user("foo", allow=Permission.SPEAK)
        >>> os.get_user("foo").describe()
        'User foo can SPEAK; cannot VIEW_CHANNEL.'
        """
        self.set(self.get_user(uid).update(allow, deny, ignore))

    def update_role(
        self,
        uid: str,
        allow: PermLike = None,
        deny: PermLike = None,
        ignore: PermLike = None,
    ):
        self.set(self.get_role(uid).update(allow, deny, ignore))
