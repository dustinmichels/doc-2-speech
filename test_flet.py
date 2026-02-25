import flet as ft

@ft.component
def App():
    path, set_path = ft.use_state("")
    print("App rendered, path:", path)
    return ft.Text("Hello")

def main(page: ft.Page):
    page.add(App())

ft.app(target=main)
