# ── Configuration ────────────────────────────────────────────────────────────
$RG         = "baby-food-tracker-rg"
$LOCATION   = "westus2"
$VM_NAME    = "baby-db-vm"
$VM_USER    = "azureuser"
$ACR_NAME   = "babyfoodtrackeracr"   # must be globally unique — change if taken
$ACA_ENV    = "baby-food-tracker-env"
$APP_NAME   = "baby-food-tracker"
$DB_USER    = "babyapp"
$DB_PASS    = "babypass"
$DB_NAME    = "babyfoods"

# ── 1. Resource group ─────────────────────────────────────────────────────────
Write-Host "`n[1/7] Creating resource group..." -ForegroundColor Cyan
az group create --name $RG --location $LOCATION

# ── 2. PostgreSQL VM ──────────────────────────────────────────────────────────
Write-Host "`n[2/7] Creating VM..." -ForegroundColor Cyan
az vm create `
  --resource-group $RG `
  --name $VM_NAME `
  --image Ubuntu2204 `
  --size Standard_B1s `
  --admin-username $VM_USER `
  --generate-ssh-keys `
  --public-ip-sku Standard

# Open port 5432 (Postgres) — locked down to ACA outbound in production
az vm open-port --resource-group $RG --name $VM_NAME --port 5432

# Get VM public IP
$VM_IP = az vm show -d -g $RG -n $VM_NAME --query publicIps -o tsv
Write-Host "VM IP: $VM_IP" -ForegroundColor Green

# ── 3. Install & configure PostgreSQL on the VM ───────────────────────────────
Write-Host "`n[3/7] Installing PostgreSQL on VM..." -ForegroundColor Cyan
$SETUP_SCRIPT = @"
#!/bin/bash
set -e
apt-get update -y
apt-get install -y postgresql postgresql-contrib

# Allow external connections
sed -i "s/#listen_addresses = 'localhost'/listen_addresses = '*'/" /etc/postgresql/14/main/postgresql.conf
echo "host all all 0.0.0.0/0 md5" >> /etc/postgresql/14/main/pg_hba.conf

systemctl restart postgresql

# Create DB user and database
sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';"
sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;"
"@

az vm run-command invoke `
  --resource-group $RG `
  --name $VM_NAME `
  --command-id RunShellScript `
  --scripts $SETUP_SCRIPT

Write-Host "PostgreSQL ready on $VM_IP:5432" -ForegroundColor Green

# ── 4. Azure Container Registry ───────────────────────────────────────────────
Write-Host "`n[4/7] Creating Container Registry..." -ForegroundColor Cyan
az acr create --resource-group $RG --name $ACR_NAME --sku Basic --admin-enabled true

# ── 5. Build & push image via ACR Tasks (no local Docker needed) ──────────────
Write-Host "`n[5/7] Building and pushing image..." -ForegroundColor Cyan
az acr build `
  --registry $ACR_NAME `
  --image baby-food-tracker:latest `
  ./app

# ── 6. Container Apps environment ─────────────────────────────────────────────
Write-Host "`n[6/7] Creating Container Apps environment..." -ForegroundColor Cyan
az containerapp env create `
  --name $ACA_ENV `
  --resource-group $RG `
  --location $LOCATION

# ── 7. Deploy the Container App ───────────────────────────────────────────────
Write-Host "`n[7/7] Deploying Container App..." -ForegroundColor Cyan
$ACR_PASSWORD = az acr credential show --name $ACR_NAME --query passwords[0].value -o tsv

az containerapp create `
  --name $APP_NAME `
  --resource-group $RG `
  --environment $ACA_ENV `
  --image "$ACR_NAME.azurecr.io/baby-food-tracker:latest" `
  --target-port 8000 `
  --ingress external `
  --registry-server "$ACR_NAME.azurecr.io" `
  --registry-username $ACR_NAME `
  --registry-password $ACR_PASSWORD `
  --env-vars "DATABASE_URL=postgresql://${DB_USER}:${DB_PASS}@${VM_IP}:5432/${DB_NAME}"

# ── Done ──────────────────────────────────────────────────────────────────────
$APP_URL = az containerapp show --name $APP_NAME --resource-group $RG --query properties.configuration.ingress.fqdn -o tsv
Write-Host "`nDone! App is live at: https://$APP_URL" -ForegroundColor Green
