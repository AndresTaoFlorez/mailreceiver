from api.routes.app_controller import create_app_controller

FirmaElectronicaController = create_app_controller(
    app_name="firma_electronica",
    path="/firma-electronica",
    tags=["Firma Electronica"],
)
