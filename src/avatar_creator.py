"""HeyGen avatar creation flow — used by PowerEEL's "Crea Avatar" page.

Wraps the HeyGen v3 API so the customer never sees HeyGen:
  1) Upload the consent video to HeyGen        → asset_id
  2) Start digital_twin training from asset_id → avatar_id (status: processing)
  3) Poll training status                       → status: processing|completed|failed
  4) When completed, the avatar is selectable in Step 4 alongside library avatars.

All calls require a HeyGen API key (the user's own, stored in their profile).
"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

HEYGEN_BASE = "https://api.heygen.com"
ASSET_UPLOAD_URL = "https://upload.heygen.com/v1/asset"


class AvatarCreatorError(RuntimeError):
    """Raised when a HeyGen avatar-creation API call fails."""


def _headers(api_key: str, content_type: str | None = None) -> dict:
    h = {"X-Api-Key": api_key}
    if content_type:
        h["Content-Type"] = content_type
    return h


def upload_video(file_path: Path, api_key: str) -> str:
    """Upload an MP4 video to HeyGen as a raw-binary POST.

    Returns the asset id which can then be referenced in /v3/avatars
    creation as `{"type": "asset_id", "asset_id": "..."}`.

    Raises AvatarCreatorError on any non-2xx response.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise AvatarCreatorError(f"File non trovato: {file_path}")

    size_mb = file_path.stat().st_size / (1024 * 1024)
    if size_mb > 32:
        raise AvatarCreatorError(
            f"File troppo grande ({size_mb:.1f} MB). HeyGen accetta max 32 MB."
        )

    logger.info("Upload video a HeyGen: %s (%.1f MB)", file_path.name, size_mb)

    with open(file_path, "rb") as f:
        body = f.read()

    resp = httpx.post(
        ASSET_UPLOAD_URL,
        content=body,
        headers=_headers(api_key, content_type="video/mp4"),
        timeout=300,
    )

    if resp.status_code >= 400:
        raise AvatarCreatorError(
            f"HeyGen upload fallito ({resp.status_code}): {resp.text[:300]}"
        )

    data = resp.json().get("data") or {}
    asset_id = data.get("id") or data.get("asset_id")
    if not asset_id:
        raise AvatarCreatorError(f"Risposta HeyGen senza asset id: {resp.text[:300]}")

    logger.info("Asset HeyGen creato: %s", asset_id)
    return asset_id


def _parse_avatar_envelope(payload: dict) -> dict:
    """Normalize the HeyGen v3 response envelope into a flat dict.

    HeyGen v3 returns:
      {"data": {"avatar_item": {...}, "avatar_group": {...}}}

    avatar_item.id is the LOOK id (used by /v2/video/generate as avatar_id).
    avatar_group.id is the GROUP id (collection of looks for the same person).
    """
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    item = data.get("avatar_item") or {}
    group = data.get("avatar_group") or {}
    # When the API returns only one object (e.g. older responses) treat it as item
    if not item and not group:
        item = data

    avatar_id = (
        item.get("id")
        or item.get("avatar_id")
        or item.get("look_id")
        or ""
    )
    group_id = (
        item.get("group_id")
        or group.get("id")
        or item.get("avatar_group_id")
        or ""
    )
    # Status may live on the item, the group, or be absent entirely on initial create
    raw_status = (
        item.get("status")
        or group.get("status")
        or item.get("training_status")
        or ""
    )
    status = (raw_status or "processing").lower()

    preview_url = (
        item.get("image_url")
        or item.get("preview_url")
        or group.get("image_url")
        or ""
    )

    return {
        "avatar_id": avatar_id,
        "group_id": group_id,
        "status": status,
        "preview_url": preview_url,
    }


def create_digital_twin(asset_id: str, name: str, api_key: str) -> dict:
    """Start training of a digital_twin avatar from a previously-uploaded asset.

    Returns a dict with at least {"avatar_id", "group_id", "status", "preview_url"}.
    Status will typically be "processing" — caller must poll get_status() until
    "completed" or "failed".
    """
    payload = {
        "type": "digital_twin",
        "name": name,
        "file": {"type": "asset_id", "asset_id": asset_id},
    }

    resp = httpx.post(
        f"{HEYGEN_BASE}/v3/avatars",
        json=payload,
        headers=_headers(api_key, content_type="application/json"),
        timeout=60,
    )

    if resp.status_code >= 400:
        raise AvatarCreatorError(
            f"HeyGen create avatar fallito ({resp.status_code}): {resp.text[:400]}"
        )

    parsed = _parse_avatar_envelope(resp.json())
    if not parsed["avatar_id"]:
        raise AvatarCreatorError(f"Risposta HeyGen senza avatar id: {resp.text[:300]}")

    return parsed


def get_status(avatar_id: str, api_key: str) -> dict:
    """Poll training status of an in-progress avatar.

    Returns {"status", "preview_url", "error"} where status is one of:
      processing | pending_consent | needs_verification | completed | failed | not_found

    A 404 from HeyGen does NOT raise — instead returns status="needs_verification"
    with a helpful hint. This happens when an avatar was created but consent
    verification hasn't been completed on HeyGen's side yet, leaving the avatar
    in a transient state where /v3/avatars/{id} returns "avatar_not_found".
    """
    resp = httpx.get(
        f"{HEYGEN_BASE}/v3/avatars/{avatar_id}",
        headers=_headers(api_key),
        timeout=15,
    )

    if resp.status_code == 404:
        return {
            "status": "needs_verification",
            "preview_url": "",
            "error": (
                "L'avatar esiste su HeyGen ma è in attesa di verifica del consenso. "
                "Vai su app.heygen.com → Avatars → 'Mio avatar' e completa la verifica, "
                "poi torna qui e clicca 'Sincronizza con HeyGen'."
            ),
        }

    if resp.status_code >= 400:
        raise AvatarCreatorError(
            f"HeyGen status fallito ({resp.status_code}): {resp.text[:300]}"
        )

    payload = resp.json()
    parsed = _parse_avatar_envelope(payload)

    err = ""
    if parsed["status"] == "failed":
        d = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        e = (d.get("avatar_item") or {}).get("error") or d.get("error") or {}
        err = e.get("message") if isinstance(e, dict) else str(e)

    return {
        "status": parsed["status"],
        "preview_url": parsed["preview_url"],
        "error": err,
    }


def _list_user_groups_v2(api_key: str) -> tuple[list[dict], dict]:
    """GET /v2/avatar_group.list → returns ONLY the user's custom groups.

    Public library groups have no train_status, custom user-trained groups do
    (values like "ready", "in_progress", "trained", "completed"). We use that
    field to skip the library and keep only the user's avatars.

    Each returned group has {"id", "name", "train_status", "preview_url"}.
    Critically the v2 endpoint returns image_url consistently — that's what
    powers the thumbnails in Step 1.
    """
    resp = httpx.get(
        f"{HEYGEN_BASE}/v2/avatar_group.list",
        headers=_headers(api_key),
        timeout=30,
    )
    if resp.status_code >= 400:
        raise AvatarCreatorError(
            f"HeyGen v2 group list fallito ({resp.status_code}): {resp.text[:400]}"
        )
    payload = resp.json()
    raw_groups = payload.get("data", {}).get("avatar_group_list", []) or []

    user_groups: list[dict] = []
    for g in raw_groups:
        if not isinstance(g, dict):
            continue
        train_status = g.get("train_status") or ""
        # Library/public avatars have no train_status. Anything else is user-owned.
        if not train_status:
            continue
        gid = g.get("id") or g.get("group_id")
        if not gid:
            continue
        user_groups.append({
            "id": gid,
            "name": g.get("name") or f"Group {gid[:8]}",
            "train_status": train_status,
            "preview_url": g.get("preview_image_url") or g.get("default_avatar_url") or "",
        })
    return user_groups, payload


def _list_avatars_in_group_v2(group_id: str, api_key: str) -> list[dict]:
    """GET /v2/avatar_group/{id}/avatars → all looks in a group with thumbnails.

    Returns a list of {"id", "name", "image_url", "status"}.
    """
    resp = httpx.get(
        f"{HEYGEN_BASE}/v2/avatar_group/{group_id}/avatars",
        headers=_headers(api_key),
        timeout=30,
    )
    if resp.status_code >= 400:
        return []
    avatars = resp.json().get("data", {}).get("avatar_list", []) or []
    out: list[dict] = []
    for av in avatars:
        if not isinstance(av, dict):
            continue
        aid = av.get("id") or av.get("avatar_id")
        if not aid:
            continue
        out.append({
            "id": aid,
            "name": av.get("name") or "Look",
            "image_url": av.get("image_url") or av.get("preview_image_url") or "",
            "status": (av.get("status") or "completed").lower(),
        })
    return out


def _list_groups(api_key: str) -> tuple[list[dict], dict]:
    """Legacy v3 wrapper kept for compatibility — unused by sync now.

    Each group has at least {"id", "name"}. Used to map look.group_id → group name.
    """
    resp = httpx.get(
        f"{HEYGEN_BASE}/v3/avatars",
        headers=_headers(api_key),
        timeout=30,
    )
    if resp.status_code >= 400:
        raise AvatarCreatorError(
            f"HeyGen list groups fallito ({resp.status_code}): {resp.text[:400]}"
        )
    payload = resp.json()
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload

    raw_list = None
    if isinstance(data, list):
        raw_list = data
    else:
        for key in ("avatars", "avatar_groups", "groups", "items", "list"):
            v = data.get(key) if isinstance(data, dict) else None
            if isinstance(v, list):
                raw_list = v
                break
    if not isinstance(raw_list, list):
        raw_list = []

    groups: list[dict] = []
    for entry in raw_list:
        if not isinstance(entry, dict):
            continue
        # Entry may be a flat group or {avatar_group: {...}}
        g = entry.get("avatar_group") if isinstance(entry.get("avatar_group"), dict) else entry
        gid = g.get("id") or g.get("group_id") or ""
        if not gid:
            continue
        groups.append({
            "id": gid,
            "name": g.get("name") or f"Group {gid[:8]}",
            "preview_url": g.get("image_url") or g.get("preview_image_url") or "",
        })
    return groups, payload


def _list_looks(api_key: str, ownership: str = "private") -> tuple[list[dict], dict]:
    """GET /v3/avatars/looks → returns (looks_list, raw_payload).

    Per HeyGen docs the response is:
      {"data": [{"id", "name", "group_id", "preview_image_url", "status"}, ...],
       "has_more": bool, "next_token": str|null}

    We follow pagination to fetch all looks.
    """
    looks: list[dict] = []
    last_payload: dict = {}
    token: str | None = None
    page = 0

    while True:
        page += 1
        params = {"limit": 50, "ownership": ownership}
        if token:
            params["token"] = token

        resp = httpx.get(
            f"{HEYGEN_BASE}/v3/avatars/looks",
            headers=_headers(api_key),
            params=params,
            timeout=30,
        )
        if resp.status_code >= 400:
            raise AvatarCreatorError(
                f"HeyGen list looks fallito ({resp.status_code}): {resp.text[:400]}"
            )

        payload = resp.json()
        last_payload = payload

        # Per docs the looks live at payload.data[]; some endpoints wrap as data.data[]
        d = payload.get("data")
        if isinstance(d, list):
            page_looks = d
            has_more = bool(payload.get("has_more"))
            next_token = payload.get("next_token")
        elif isinstance(d, dict):
            page_looks = d.get("looks") or d.get("items") or d.get("list") or []
            has_more = bool(d.get("has_more"))
            next_token = d.get("next_token")
        else:
            page_looks = []
            has_more = False
            next_token = None

        for lk in page_looks:
            if not isinstance(lk, dict):
                continue
            lid = lk.get("id") or lk.get("look_id") or lk.get("avatar_id")
            if not lid:
                continue
            looks.append({
                "id": lid,
                "name": lk.get("name") or f"Look {lid[:8]}",
                "group_id": lk.get("group_id") or "",
                "status": (lk.get("status") or "completed").lower(),
                "preview_url": (
                    lk.get("preview_image_url")
                    or lk.get("image_url")
                    or lk.get("preview_url")
                    or ""
                ),
                "error": lk.get("error"),
            })

        if not has_more or not next_token or page > 20:
            break
        token = next_token

    return looks, last_payload


def list_remote_avatars(
    api_key: str, return_raw: bool = False,
) -> list[dict] | tuple[list[dict], dict]:
    """Build a flat list of LOOKS (one entry per selectable avatar variant).

    Uses v2 endpoints because v2 returns image_url consistently for custom
    avatars (v3's preview_image_url is empty for in-training looks). Skips
    public library by filtering on the train_status field which is only set
    for user-trained avatars.

    Returns a list of:
      {
        "avatar_id":   "<look id, used by /v2/video/generate>",
        "group_id":    "<group id>",
        "name":        "<group name, e.g. 'Mio avatar'>",
        "look_name":   "<look name, e.g. 'Podcaster in black ribbed sweater'>",
        "status":      "completed" | "processing" | "failed" | ...,
        "preview_url": "<image url>",
      }
    """
    user_groups, groups_raw = _list_user_groups_v2(api_key)
    group_avatars_raw: dict[str, list] = {}

    out: list[dict] = []
    for g in user_groups:
        looks_in_group = _list_avatars_in_group_v2(g["id"], api_key)
        group_avatars_raw[g["id"]] = looks_in_group

        # Map the v2 group's train_status to our normalised status
        # (e.g. "trained" → "completed", "in_progress" → "processing")
        gstatus = g.get("train_status", "").lower()
        default_status = (
            "completed" if gstatus in ("trained", "ready", "completed", "done") else
            "processing" if gstatus in ("in_progress", "training", "pending") else
            "completed"
        )

        if not looks_in_group:
            # Group exists but no avatars yet — synthesise one entry so the
            # user sees the group at all (with the group preview if any)
            out.append({
                "avatar_id": g["id"],
                "group_id": g["id"],
                "name": g["name"],
                "look_name": g["name"],
                "status": default_status,
                "preview_url": g.get("preview_url", ""),
            })
            continue

        for lk in looks_in_group:
            out.append({
                "avatar_id": lk["id"],
                "group_id": g["id"],
                "name": g["name"],
                "look_name": lk.get("name"),
                "status": lk.get("status") or default_status,
                "preview_url": lk.get("image_url", ""),
            })

    if return_raw:
        return out, {
            "v2_groups": groups_raw,
            "v2_avatars_per_group": group_avatars_raw,
        }
    return out


def upload_and_train(file_path: Path, name: str, api_key: str) -> dict:
    """Convenience: upload + start training in one call.

    Returns the same dict as create_digital_twin().
    """
    asset_id = upload_video(file_path, api_key)
    return create_digital_twin(asset_id, name, api_key)
