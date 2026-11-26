"""Segmentation and digital pattern making for uploaded garments.

Pipeline: analyzer -> segmenter -> flatten (2D patterns) -> editor (modify and
rebuild) -> validation. The uploaded file is never modified: every step works on
copies of its vertices.
"""
