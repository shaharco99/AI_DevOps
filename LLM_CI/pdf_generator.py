"""
PDF generation module for database query results.
Converts query results into formatted PDF documents with tables.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional


def generate_pdf_from_results(
    query_results: List[Dict[str, Any]],
    query: str,
    title: str = 'Database Query Results',
    output_file: Optional[str] = None
) -> str:
    """
    Generate a PDF file from database query results.

    Args:
        query_results: List of dictionaries containing query results
        query: The SQL query that was executed
        title: Title for the PDF document
        output_file: Path to save the PDF. If None, generates a timestamped filename

    Returns:
        Path to the generated PDF file
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError:
        raise ImportError('reportlab not installed. Please install it with: pip install reportlab')

    if not output_file:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        # Default to a visible folder in the current working directory unless overridden
        default_dir = os.getenv('PDF_OUTPUT_DIR') or os.getcwd()
        output_dir = os.path.abspath(default_dir)
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, f"query_results_{timestamp}.pdf")

    try:
        # Create PDF document
        doc = SimpleDocTemplate(output_file, pagesize=letter)
        story = []
        styles = getSampleStyleSheet()

        # Title
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=16,
            textColor=colors.HexColor('#1f4788'),
            spaceAfter=30,
            alignment=TA_CENTER,
        )
        story.append(Paragraph(title, title_style))

        # Query section
        query_style = ParagraphStyle(
            'QueryStyle',
            parent=styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#666666'),
            spaceAfter=10,
            leftIndent=10,
            rightIndent=10,
            fontName='Courier',
        )
        story.append(Paragraph('<b>Query:</b>', styles['Normal']))
        story.append(Paragraph(f"<font face='Courier' size='8'>{query}</font>", query_style))
        story.append(Spacer(1, 0.2 * inch))

        # Metadata
        metadata_style = ParagraphStyle(
            'MetadataStyle',
            parent=styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#999999'),
            spaceAfter=15,
        )
        generated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        story.append(Paragraph(
            f"<b>Generated:</b> {generated_at} | <b>Rows:</b> {len(query_results)}",
            metadata_style,
        ))

        story.append(Spacer(1, 0.2 * inch))

        # Results table
        if query_results:
            # Prepare table data
            columns = list(query_results[0].keys())
            table_data = [columns]  # Header row

            for row in query_results:
                row_data = []
                for col in columns:
                    value = row.get(col, '')
                    # Convert None to empty string, format other types
                    if value is None:
                        value = ''
                    elif not isinstance(value, str):
                        value = str(value)
                    # Truncate very long values
                    if len(value) > 100:
                        value = value[:97] + '...'
                    row_data.append(value)
                table_data.append(row_data)

            # Create table with styling
            col_widths = [letter[0] / len(columns) - 0.1 * inch for _ in columns]
            table = Table(table_data, colWidths=col_widths)

            table.setStyle(TableStyle([
                # Header styling
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),

                # Row styling
                ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f0f0')]),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#cccccc')),
                ('TOPPADDING', (0, 1), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))

            story.append(table)
        else:
            story.append(Paragraph('<i>No results returned from query</i>', styles['Normal']))

        # Build PDF
        doc.build(story)

        # Ensure file was created
        if not os.path.exists(output_file):
            raise Exception(f"PDF generation reported success but file not found: {output_file}")

        return os.path.abspath(output_file)

    except Exception as e:
        raise Exception(f"Error generating PDF: {e}")


def generate_pdf_from_json(
    json_data: str,
    title: str = 'Database Query Results',
    output_file: Optional[str] = None
) -> str:
    """
    Generate a PDF from JSON string containing query results.

    Args:
        json_data: JSON string with query results
        title: Title for the PDF document
        output_file: Path to save the PDF

    Returns:
        Path to the generated PDF file
    """
    try:
        data = json.loads(json_data)

        # Extract query and results
        query = data.get('query', 'Unknown Query')
        results = data.get('results', [])

        return generate_pdf_from_results(
            query_results=results,
            query=query,
            title=title,
            output_file=output_file,
        )
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON data: {e}")


def format_results_as_table(
    query_results: List[Dict[str, Any]],
    max_width: int = 120
) -> str:
    """
    Format query results as an ASCII table string.

    Args:
        query_results: List of dictionaries containing query results
        max_width: Maximum width for the table

    Returns:
        Formatted ASCII table string
    """
    if not query_results:
        return 'No results'

    # Get columns
    columns = list(query_results[0].keys())

    # Calculate column widths
    col_widths = {}
    for col in columns:
        max_len = len(col)
        for row in query_results:
            val = str(row.get(col, ''))
            if len(val) > max_len:
                max_len = len(val)
        col_widths[col] = min(max_len, 30)  # Cap at 30 characters

    # Create separator
    separator = '+' + '+'.join(['-' * (col_widths[col] + 2) for col in columns]) + '+'

    # Create header
    header = '|'
    for col in columns:
        header += f" {col:<{col_widths[col]}} |"

    # Create rows
    rows = []
    for data_row in query_results:
        row = '|'
        for col in columns:
            val = str(data_row.get(col, ''))
            if len(val) > col_widths[col]:
                val = val[:col_widths[col] - 3] + '...'
            row += f" {val:<{col_widths[col]}} |"
        rows.append(row)

    # Assemble table
    table = separator + '\n' + header + '\n' + separator + '\n' + '\n'.join(rows) + '\n' + separator

    return table
