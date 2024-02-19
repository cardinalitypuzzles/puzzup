import json
from typing import Dict

from discord_interactions import verify_key  # type: ignore
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from puzzle_editing.models import Puzzle


@csrf_exempt
def slashCommandHandler(request):
    if not verify_key(
        request.body,
        request.headers["X-Signature-Ed25519"],
        request.headers["X-Signature-Timestamp"],
        settings.DISCORD_APP_PUBLIC_KEY,
    ):
        return HttpResponse("invalid request signature", status=401)
    payload = json.loads(request.body)
    if payload["type"] == 1:
        # this is a ping
        return pingHandler()
    elif payload["type"] == 2:
        if payload["data"]["name"] == "up":
            if payload["data"]["options"][0]["type"] == 1:
                if payload["data"]["options"][0]["name"] == "info":
                    return puzzleInfoHandler(request, payload)
                elif payload["data"]["options"][0]["name"] == "url":
                    return puzzleLinkHandler(request, payload)
                else:
                    return genericHandler(payload)
    raise NotImplementedError


def pingHandler():
    return JsonResponse({"type": 1})


def genericHandler(payload):
    return JsonResponse({"type": 4, "data": {"content": json.dumps(payload)}})


def _puzzleInfoHelper(puzzle: Dict) -> str:
    return (
        f"Codename: {puzzle['codename']}\n"
        f"Name: ||{puzzle['name']}||\n"
        f"This puzzle has status **{puzzle['status']}**!\n"
        f"Access it at <{puzzle['url']}>\n"
        f"Brainstorming/solution sheet: <{puzzle['solution']}>\n"
        f"Author(s): {puzzle['authors']}"
    )


def puzzleInfoHandler(request, payload):
    puzzle = (
        Puzzle.objects.filter(discord_channel_id=payload["channel_id"])
        .prefetch_related("authors")
        .order_by("name")
    )
    responseJson = {"type": 4}
    puzzles = [
        {
            "name": p.name,
            "id": p.id,
            "codename": p.codename,
            "summary": p.summary,
            "description": p.description,
            "status": p.get_status_display(),
            "url": external_puzzle_url(request, p),
            "solution": p.solution,
            "authors": p.author_list,
        }
        for p in puzzle
    ]
    responsetext = ""
    if len(puzzles) > 1:
        responsetext += ":warning: This puzzle is linked to multiple puzzles!\n"

    elif len(puzzles) > 0:
        responsetext += "\n".join([_puzzleInfoHelper(p) for p in puzzles])

    else:
        responsetext += ":information_source: This channel is not linked to any puzzles"

    responseJson["data"] = {"content": responsetext}
    return JsonResponse(responseJson)


def puzzleLinkHandler(request, payload):
    puzzle = Puzzle.objects.filter(discord_channel_id=payload["channel_id"])
    responseJson = {"type": 4}
    puzzles = [
        {
            "name": p.name,
            "id": p.id,
            "codename": p.codename,
            "summary": p.summary,
            "description": p.description,
        }
        for p in puzzle
    ]
    responsetext = ""
    if len(puzzles) > 1:
        responsetext += ":warning: This puzzle is linked to multiple puzzles!\n"

    elif len(puzzles) > 0:
        responsetext += "\n".join(
            [
                "<https://{}/puzzle/{}>".format(request.META["HTTP_HOST"], p["id"])
                for p in puzzles
            ]
        )

    else:
        responsetext += ":information_source: This channel is not linked to any puzzles"

    responseJson["data"] = {"content": responsetext}
    return JsonResponse(responseJson)
