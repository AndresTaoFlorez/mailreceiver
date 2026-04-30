from api.presentation.routes.app_controller import create_app_controller

JusticiaXxiWebController = create_app_controller(
    app_name="justicia_xxi_web",
    path="/justicia-xxi-web",
    tags=["Justicia XXI Web"],
    assign_specialists=True,
)
