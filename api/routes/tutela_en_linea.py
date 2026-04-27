from api.routes.app_controller import create_app_controller

TutelaEnLineaController = create_app_controller(
    app_name="tutela_en_linea",
    path="/tutela-en-linea",
    tags=["Tutela en Linea"],
)
