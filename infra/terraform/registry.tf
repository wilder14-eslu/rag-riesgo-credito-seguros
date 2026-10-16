resource "azurerm_container_registry" "main" {
  # El SKU Basic no admite red privada, zonas, réplicas, cuarentena ni retención; el escaneo de
  # vulnerabilidades se hace con Trivy en CI antes de publicar la imagen. En prod: Premium.
  #checkov:skip=CKV_AZURE_139:Basic no admite red privada
  #checkov:skip=CKV_AZURE_233:Basic no admite redundancia de zona
  #checkov:skip=CKV_AZURE_237:Basic no admite endpoints de datos dedicados
  #checkov:skip=CKV_AZURE_164:Imágenes firmadas requieren Premium
  #checkov:skip=CKV_AZURE_165:Un solo región en dev
  #checkov:skip=CKV_AZURE_166:Cuarentena requiere Premium; Trivy en CI cumple el rol
  #checkov:skip=CKV_AZURE_167:Política de retención requiere Premium
  #checkov:skip=CKV_AZURE_163:Escaneo con Trivy en CI
  name                = "acr${local.name_alt}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "Basic"
  admin_enabled       = false # la descarga se hace con la identidad administrada (AcrPull)
  tags                = local.tags
}
