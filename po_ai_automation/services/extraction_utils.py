import re


_LABELED_ITEM_CODE_PATTERN = re.compile(
    r"""
    (?<![A-Za-z0-9])
    (?:
        (?:customer\s+)?(?:item\s+)?(?:part\s+)?(?:code|no\.?|number|id)
        |
        (?:item|part|product|material|catalog(?:ue)?|article|ref(?:erence)?|model|sku)
        (?:\s*(?:code|no\.?|number|id))?
        |
        code
    )
    \s*(?:[-:#=]\s*|\s+)
    ([A-Za-z0-9](?:[A-Za-z0-9._/-]*[A-Za-z0-9])?)
    """,
    re.IGNORECASE | re.VERBOSE,
)

_ITEM_CODE_FIELDS = (
    "customer_item_code",
    "customer_part_no",
    "part_number",
    "part_no",
    "product_code",
    "material_code",
    "sku",
    "item_number",
    "code",
)

_STANDALONE_ITEM_CODE_PATTERN = re.compile(
    r"""
    ^
    ([A-Za-z0-9][A-Za-z0-9._/]*(?:\s*-\s*[A-Za-z0-9][A-Za-z0-9._/]*)*)
    $
    """,
    re.VERBOSE,
)


def populate_item_codes_from_descriptions(po_data):
    """
    Fill missing item codes from code fields or code-shaped descriptions.

    A description is used only when it contains a labeled code or consists
    entirely of a compact, code-shaped identifier. Item validation still uses
    the resulting item_code field only.
    """

    for item in po_data.get("items") or []:
        item_code = item.get("item_code")

        if item_code is None or not str(item_code).strip():
            item_code = next(
                (
                    item.get(fieldname)
                    for fieldname in _ITEM_CODE_FIELDS
                    if item.get(fieldname) is not None
                    and str(item.get(fieldname)).strip()
                ),
                None,
            )

        if item_code is not None and str(item_code).strip():
            item["item_code"] = str(item_code).strip()
            continue

        description = item.get("description")

        if not isinstance(description, str):
            continue

        match = _LABELED_ITEM_CODE_PATTERN.search(description)

        if match:
            item["item_code"] = match.group(1)
            continue

        standalone_match = _STANDALONE_ITEM_CODE_PATTERN.fullmatch(
            description.strip()
        )
        if standalone_match:
            candidate = standalone_match.group(1)
            if (
                len(re.sub(r"[^A-Za-z0-9]", "", candidate)) >= 5
                and re.search(r"[A-Za-z]", candidate)
                and re.search(r"\d", candidate)
            ):
                item["item_code"] = re.sub(r"\s*-\s*", "-", candidate)

    return po_data
