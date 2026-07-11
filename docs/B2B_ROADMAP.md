# MiMo Mobile — B2B Transition Roadmap

## Estado Actual vs Requerido B2B

| Feature | Premium | B2B Starter | B2B Enterprise |
|---------|---------|-------------|----------------|
| Multi-tenancy | No | Organizaciones | Organizaciones + Custom |
| RBAC | PIN simple | Admin/Manager/User | + SSO/SAML |
| Audit Log | No | Básico | + Export, Compliance |
| API Keys | Simple | Por equipo | + Rate limits, Scopes |
| Billing | Fijo | Por uso | + Invoice, SLA |
| Self-hosted | No | No | Docker/K8s |
| Support | Email | Priority | Dedicated |

---

## Fase 1: Multi-Tenancy + RBAC (1-2 semanas)

**Ya implementado en `b2b.py`:**

```python
# Crear organización
org = b2b.create_organization("Acme Corp", owner_user_id="user123")

# Agregar miembros
b2b.add_member(org.id, "user456", Role.MANAGER)

# Verificar permisos
if b2b.check_permission(org.id, user_id, "projects.manage"):
    # Allow action
    pass

# Audit log
b2b.log_event(org.id, user_id, "project.created", "project", "proj_123")
```

### Endpoints API

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/api/org/create` | POST | Crear organización |
| `/api/org/list` | GET | Listar orgs del usuario |
| `/api/org/:id` | GET | Obtener org |
| `/api/org/:id/members` | GET | Listar miembros |
| `/api/org/:id/invite` | POST | Invitar miembro |
| `/api/org/accept-invite` | POST | Aceptar invitación |
| `/api/org/:id/audit` | GET | Audit log |
| `/api/org/:id/api-keys` | POST | Crear API key |

---

## Fase 2: Billing por Uso (2-3 semanas)

### Modelo de Precios B2B

| Plan | Precio | Incluye |
|------|--------|---------|
| **Starter** | $49/mes | 5 usuarios, 10K mensajes |
| **Business** | $199/mes | 25 usuarios, 100K mensajes |
| **Enterprise** | Custom | Ilimitado, SLA, soporte dedicado |

### Implementación

```python
# Usage tracking
class UsageTracker:
    def track_message(self, org_id: str, user_id: str, tokens: int):
        # Store in Redis/DB
        pass
    
    def get_monthly_usage(self, org_id: str) -> dict:
        # Return current month usage
        pass
    
    def check_limit(self, org_id: str) -> bool:
        # Check if org exceeded plan limits
        pass
```

### Integración con Stripe

```python
# Create subscription
stripe.Subscription.create(
    customer=org.stripe_customer_id,
    items=[{"price": plan_price_id}],
    metadata={"org_id": org.id}
)

# Webhook para usage-based billing
@app.post("/webhook/stripe")
def handle_stripe_webhook(event):
    if event["type"] == "invoice.paid":
        # Reset usage counters
        pass
```

---

## Fase 3: Enterprise Features (1-2 meses)

### 3.1 SSO/SAML

```python
# Integración con Identity Providers
from saml2 import Client
from saml2.response import ValidResponse

class SAMLAuth:
    def __init__(self, org_id: str):
        self.org = b2b.get_organization(org_id)
        self.saml_config = self.org.settings.get("saml", {})
    
    def create_login_request(self) -> str:
        # Generate SAML AuthnRequest
        pass
    
    def validate_response(self, response: str) -> dict:
        # Validate SAML Response
        pass
```

### 3.2 Custom Domains

```python
# Per-tenant custom domain
class CustomDomain:
    def __init__(self, org_id: str, domain: str):
        self.org_id = org_id
        self.domain = domain
    
    def verify(self) -> bool:
        # DNS TXT record verification
        pass
    
    def setup_ssl(self):
        # Auto-provision SSL certificate
        pass
```

### 3.3 Self-Hosted Option

```yaml
# docker-compose.enterprise.yml
version: '3.8'
services:
  mimo-server:
    image: mimo-enterprise:latest
    environment:
      - MIMO_LICENSE_KEY=${LICENSE_KEY}
      - MIMO_ORG_ID=${ORG_ID}
      - MIMO_SSO_ENABLED=true
    volumes:
      - ./config:/config
      - ./data:/data
```

---

## Fase 4: Compliance & Security (2-3 meses)

### 4.1 SOC2 Compliance

- [ ] Access controls documentation
- [ ] Audit logging (implementado)
- [ ] Data encryption at rest
- [ ] Incident response plan
- [ ] Annual security assessment

### 4.2 GDPR Compliance

- [ ] Data export API
- [ ] Right to deletion
- [ ] Consent management
- [ ] Data processing agreements

### 4.3 HIPAA (si aplica)

- [ ] BAA (Business Associate Agreement)
- [ ] PHI encryption
- [ ] Access controls
- [ ] Audit trails

---

## Métricas Clave B2B

| Métrica | Target | Descripción |
|---------|--------|-------------|
| **ARR** | $100K+ | Annual Recurring Revenue |
| **NRR** | >110% | Net Revenue Retention |
| **CAC** | <$500 | Customer Acquisition Cost |
| **LTV** | >$5K | Lifetime Value |
| **Churn** | <5% | Monthly churn rate |
| **NPS** | >50 | Net Promoter Score |

---

## Checklist de Lanzamiento B2B

### Legal
- [ ] Terms of Service actualizado
- [ ] Privacy Policy (GDPR)
- [ ] DPA (Data Processing Agreement)
- [ ] SLA terms

### Infraestructura
- [ ] Multi-region deployment
- [ ] Auto-scaling
- [ ] Backup & disaster recovery
- [ ] Monitoring & alerting

### Sales
- [ ] Pricing page
- [ ] Demo environment
- [ ] Sales collateral
- [ ] Partner program

### Support
- [ ] Documentation
- [ ] Knowledge base
- [ ] Ticketing system
- [ ] Dedicated support (Enterprise)
