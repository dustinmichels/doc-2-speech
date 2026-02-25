import os
import threading

import flet as ft

from pipeline import extract_pdf, refine_text, text_to_speech

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

STAGES = ["Extract text", "Refine text", "Generate audio"]


def main(page: ft.Page):
    page.title = "PDF to Speech"
    page.padding = 30
    page.window.width = 480
    page.window.height = 420

    selected_path = ft.Ref[str]()
    selected_path.current = None

    # --- File picker ---
    file_picker = ft.FilePicker()
    page.overlay.append(file_picker)
    page.update()

    path_label = ft.Text("No document selected", color=ft.Colors.GREY_500, size=13)

    def on_file_picked(e):
        if e.files:
            selected_path.current = e.files[0].path
            path_label.value = os.path.basename(selected_path.current)
            path_label.color = ft.Colors.ON_SURFACE
            run_btn.disabled = False
        page.update()

    file_picker.on_result = on_file_picked

    choose_btn = ft.OutlinedButton(
        "Choose a document",
        icon=ft.Icons.UPLOAD_FILE,
        on_click=lambda _: file_picker.pick_files(
            allowed_extensions=["pdf"], allow_multiple=False
        ),
    )

    # --- Stage rows ---
    def make_stage_row(label):
        indicator = ft.Container(
            width=22,
            height=22,
            border_radius=11,
            bgcolor=ft.Colors.GREY_300,
        )
        return ft.Row(
            [indicator, ft.Text(label, size=14)],
            spacing=12,
        ), indicator

    stage_rows = []
    stage_indicators = []
    for label in STAGES:
        row, indicator = make_stage_row(label)
        stage_rows.append(row)
        stage_indicators.append(indicator)

    stages_column = ft.Column(stage_rows, spacing=10, visible=False)

    # --- Run button ---
    run_btn = ft.FilledButton("Run", disabled=True, on_click=None)

    def set_stage_running(i):
        stage_indicators[i].content = ft.ProgressRing(
            width=16, height=16, stroke_width=2
        )
        stage_indicators[i].bgcolor = ft.Colors.TRANSPARENT
        page.update()

    def set_stage_done(i):
        stage_indicators[i].content = ft.Icon(
            ft.Icons.CHECK_CIRCLE, color=ft.Colors.GREEN, size=22
        )
        stage_indicators[i].bgcolor = ft.Colors.TRANSPARENT
        page.update()

    def set_stage_error(i):
        stage_indicators[i].content = ft.Icon(
            ft.Icons.ERROR, color=ft.Colors.RED, size=22
        )
        stage_indicators[i].bgcolor = ft.Colors.TRANSPARENT
        page.update()

    def reset_stages():
        for ind in stage_indicators:
            ind.content = None
            ind.bgcolor = ft.Colors.GREY_300

    def run_pipeline(_):
        pdf_path = selected_path.current
        if not pdf_path:
            return

        run_btn.disabled = True
        reset_stages()
        stages_column.visible = True
        page.update()

        pdf_stem = os.path.splitext(os.path.basename(pdf_path))[0]
        output_dir = os.path.join(PROJECT_ROOT, "out", pdf_stem)

        steps = [
            lambda: extract_pdf(pdf_path, output_dir),
            lambda: refine_text(output_dir),
            lambda: text_to_speech(output_dir),
        ]

        success = True
        for i, step in enumerate(steps):
            set_stage_running(i)
            try:
                step()
                set_stage_done(i)
            except Exception as exc:
                set_stage_error(i)
                success = False
                break

        run_btn.disabled = False
        page.update()

    run_btn.on_click = lambda e: threading.Thread(
        target=run_pipeline, args=(e,), daemon=True
    ).start()

    # --- Layout ---
    page.add(
        ft.Column(
            [
                ft.Text("PDF to Speech", size=22, weight=ft.FontWeight.BOLD),
                ft.Divider(height=16, color=ft.Colors.TRANSPARENT),
                ft.Row(
                    [choose_btn, path_label],
                    spacing=14,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Divider(height=8, color=ft.Colors.TRANSPARENT),
                run_btn,
                ft.Divider(height=20, color=ft.Colors.TRANSPARENT),
                stages_column,
            ],
            spacing=4,
        )
    )


ft.run(main)
