from api.presentation.routes.app_controller import create_app_controller

DemandaEnLineaController = create_app_controller(
    app_name="demanda_en_linea",
    path="/demanda-en-linea",
    tags=["Demanda en Linea"],
)
