# Guardrail de Bedrock: ataques de prompt, PII (incluye DNI y RUC de Perú), temas
# denegados y verificación de grounding. Se aplica con la API ApplyGuardrail.

resource "aws_bedrock_guardrail" "main" {
  name                      = local.name
  description               = "Guardrail del asistente de riesgo crediticio y seguros"
  blocked_input_messaging   = "No puedo procesar esta solicitud. Puedo ayudarte con preguntas de riesgo crediticio y seguros."
  blocked_outputs_messaging = "No puedo entregar esta respuesta porque no cumple las políticas de seguridad."
  kms_key_arn               = aws_kms_key.main.arn

  content_policy_config {
    filters_config {
      type            = "PROMPT_ATTACK"
      input_strength  = "HIGH"
      output_strength = "NONE"
    }
    filters_config {
      type            = "MISCONDUCT"
      input_strength  = "HIGH"
      output_strength = "HIGH"
    }
    filters_config {
      type            = "INSULTS"
      input_strength  = "MEDIUM"
      output_strength = "MEDIUM"
    }
    filters_config {
      type            = "HATE"
      input_strength  = "MEDIUM"
      output_strength = "MEDIUM"
    }
  }

  sensitive_information_policy_config {
    pii_entities_config {
      type   = "EMAIL"
      action = "ANONYMIZE"
    }
    pii_entities_config {
      type   = "PHONE"
      action = "ANONYMIZE"
    }
    pii_entities_config {
      type   = "CREDIT_DEBIT_CARD_NUMBER"
      action = "BLOCK"
    }
    pii_entities_config {
      type   = "NAME"
      action = "ANONYMIZE"
    }
    regexes_config {
      name        = "dni_peru"
      description = "DNI peruano precedido de la palabra DNI"
      pattern     = "(?i)dni\\s*[:#]?\\s*\\d{8}"
      action      = "ANONYMIZE"
    }
    regexes_config {
      name        = "ruc_peru"
      description = "RUC peruano de 11 digitos"
      pattern     = "\\b(10|15|17|20)\\d{9}\\b"
      action      = "ANONYMIZE"
    }
  }

  topic_policy_config {
    topics_config {
      name       = "asesoria_inversion_personal"
      type       = "DENY"
      definition = "Recomendaciones personalizadas de inversión, compra o venta de activos financieros."
      examples   = ["¿En qué acciones debo invertir mis ahorros?", "¿Me conviene comprar este bono?"]
    }
    topics_config {
      name       = "evadir_regulacion"
      type       = "DENY"
      definition = "Instrucciones para evadir la regulación, ocultar morosidad o manipular la clasificación de deudores."
      examples   = ["¿Cómo oculto créditos vencidos al supervisor?"]
    }
  }

  contextual_grounding_policy_config {
    filters_config {
      type      = "GROUNDING"
      threshold = 0.75
    }
    filters_config {
      type      = "RELEVANCE"
      threshold = 0.5
    }
  }
}

resource "aws_bedrock_guardrail_version" "main" {
  guardrail_arn = aws_bedrock_guardrail.main.guardrail_arn
  description   = "Versión publicada para ${var.environment}"
  skip_destroy  = true

  # Publicar una versión nueva cada vez que cambie la configuración del guardrail
  lifecycle {
    replace_triggered_by = [aws_bedrock_guardrail.main]
  }
}
