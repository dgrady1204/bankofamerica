"""
Created on May 2, 2025

@author: DGRADY
"""

import logging
import io

from pdfminer.pdfparser import PDFParser
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfpage import PDFTextExtractionNotAllowed
from pdfminer.pdfinterp import PDFResourceManager
from pdfminer.pdfinterp import PDFPageInterpreter
from pdfminer.layout import LAParams
from pdfminer.converter import PDFPageAggregator
import pdfminer

import pdfminer.high_level
import pdfminer.layout

logger = logging.getLogger(__name__)


def extract_statement_pages(pdf_file):
    """
    Extract the pages from a PDF statement.
    """
    pages = extract_pages_from_statement_pdf(pdf_file)
    page_lines = {}
    for page_count, _ in enumerate(pages):
        page_lines[page_count] = get_page_text_from_pdf_elements(pages[page_count])
    return page_lines


def extract_pages_from_statement_pdf(pdf_data):
    """
    Extracts LTPage objects from a pdf file.

    slightly modified from
    https://euske.github.io/pdfminer/programming.html
    """
    laparams = LAParams()

    # Create a file-like object from the bytes data
    with io.BytesIO(pdf_data) as file:
        parser = PDFParser(file)
        document = PDFDocument(parser)
        if not document.is_extractable:
            raise PDFTextExtractionNotAllowed

        rsrcmgr = PDFResourceManager()
        device = PDFPageAggregator(rsrcmgr, laparams=laparams)
        interpreter = PDFPageInterpreter(rsrcmgr, device)

        layouts = []
        for page in PDFPage.create_pages(document):
            interpreter.process_page(page)
            temp_device = device.get_result()
            layouts.append(temp_device)

    return layouts


def get_page_text_from_pdf_elements(page):
    """
    Extracts text from a page of a pdf file.
    """
    lines = []
    r = 0
    y0 = 0
    y1 = 0

    page_size = page.y1
    for e in page:
        if isinstance(e, pdfminer.layout.LTTextBoxHorizontal):
            if page_size > 0:
                y0 = page_size - e.y0
                y1 = page_size - e.y1
            e.y0 = str(int(round(y0, r))).zfill(3)
            e.y1 = str(int(round(y1, r))).zfill(3)
            e.x0 = str(int(round(e.x0, r))).zfill(3)
            e.x1 = str(int(round(e.x1, r))).zfill(3)
            line_text = e.get_text().replace("\n", " ").strip()
            line_sort = e.y0 + "." + e.y1 + "." + e.x0 + "." + e.x1
            lines.append([line_sort, line_text])

    lines_comb = []
    for i, c in enumerate(lines):
        if i == 0:
            lines_comb.append(c)
        else:
            found = False
            for x, _ in enumerate(lines_comb):
                if (
                    lines_comb[x][0].split(".")[0] == c[0].split(".")[0]
                    or lines_comb[x][0].split(".")[1] == c[0].split(".")[1]
                ):
                    if c[0].split(".")[2] < lines_comb[x][0].split(".")[2]:
                        lines_comb[x][1] = c[1] + " " + lines_comb[x][1]
                    else:
                        lines_comb[x][1] = lines_comb[x][1] + " " + c[1]
                    found = True
                    break
            if not found:
                lines_comb.append(c)

    return [l[-1] for l in lines_comb]


if __name__ == "__main__":
    pass
