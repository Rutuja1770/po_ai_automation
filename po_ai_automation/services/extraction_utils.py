import re


_LABELED_ITEM_CODE_PATTERN = re.compile(
    r"""
    (?<![A-Za-z0-9])
    (?:
        customer\s+(?:item\s+)?(?:part\s+)?(?:code|no\.?|number)
        |
        (?:item|part|product|material|catalog(?:ue)?|article|ref(?:erence)?|model|sku)
        (?:\s*(?:code|no\.?|number))?
    )
    \s*(?:[-:#=]\s*|\s+)
    ([A-Za-z0-9](?:[A-Za-z0-9._/-]*[A-Za-z0-9])?)
    """,
    re.IGNORECASE | re.VERBOSE,
)


def populate_item_codes_from_descriptions(po_data):
    """
    Fill missing item codes from explicitly labeled codes in item descriptions.

    The description is only a source for extracting a clearly labeled code;
    item validation still uses the resulting item_code field only.
    """

    for item in po_data.get("items") or []:
        if item.get("item_code"):
            continue

        description = item.get("description")

        if not isinstance(description, str):
            continue

        match = _LABELED_ITEM_CODE_PATTERN.search(description)

        if match:
            item["item_code"] = match.group(1)

    return po_data
