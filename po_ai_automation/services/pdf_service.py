import fitz


def extract_text_from_pdf(file_path):

    document = fitz.open(file_path)

    page_count = len(document)

    pages = []

    for page in document:

        text = page.get_text("text")

        if text and text.strip():
            pages.append(text.strip())

    document.close()

    full_text = "\n".join(pages).strip()

    return {
        "is_text_pdf": bool(full_text),
        "text": full_text,
        "page_count": page_count
    }
# import fitz


# def extract_text_from_pdf(file_path):
#     """
#     Extract selectable text from a PDF.

#     Returns:
#         str: Extracted text
#     """

#     document = fitz.open(file_path)

#     pages = []

#     for page in document:
#         text = page.get_text("text")

#         if text:
#             pages.append(text)

#     document.close()

#     return "\n".join(pages).strip()