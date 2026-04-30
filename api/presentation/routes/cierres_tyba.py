from api.presentation.routes.app_controller import create_app_controller

CierresTybaController = create_app_controller(
    app_name="cierres_tyba",
    path="/cierres-tyba",
    tags=["Cierres TYBA"],
)
