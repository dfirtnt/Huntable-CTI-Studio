#!/bin/bash

# Generate self-signed SSL certificates for local development
# This allows HTTPS access from iPhone on local network

set -e

CERT_DIR="/etc/nginx/ssl"
HOSTNAME=$(hostname)
IP_ADDRESS=$(hostname -I | awk '{print $1}')

echo "Generating SSL certificates for local development..."
echo "Hostname: $HOSTNAME"
echo "IP Address: $IP_ADDRESS"

# Create certificate directory
mkdir -p "$CERT_DIR"

# Generate private key
openssl genrsa -out "$CERT_DIR/key.pem" 2048

# Generate certificate signing request
openssl req -new -key "$CERT_DIR/key.pem" -out "$CERT_DIR/cert.csr" -subj "/C=US/ST=State/L=City/O=Organization/CN=$HOSTNAME"

# Generate self-signed certificate
openssl x509 -req -days 365 -in "$CERT_DIR/cert.csr" -signkey "$CERT_DIR/key.pem" -out "$CERT_DIR/cert.pem" \
    -extensions v3_req -extfile <(
        cat <<EOF
[v3_req]
basicConstraints = CA:FALSE
keyUsage = nonRepudiation, digitalSignature, keyEncipherment
subjectAltName = @alt_names

[alt_names]
DNS.1 = localhost
DNS.2 = $HOSTNAME
IP.1 = 127.0.0.1
IP.2 = $IP_ADDRESS
EOF
    )

# Set proper permissions
chmod 600 "$CERT_DIR/key.pem"
chmod 644 "$CERT_DIR/cert.pem"

# Clean up CSR
rm "$CERT_DIR/cert.csr"

echo "SSL certificates generated successfully!"
echo "Certificate: $CERT_DIR/cert.pem"
echo "Private Key: $CERT_DIR/key.pem"
echo ""
echo "To access from iPhone:"
echo "1. Find your Mac's IP address: $IP_ADDRESS"
echo "2. Open Safari on iPhone"
echo "3. Go to: https://$IP_ADDRESS"
echo "4. Accept the security warning (self-signed certificate)"
echo ""
echo "Note: You may need to trust the certificate in iPhone Settings > General > About > Certificate Trust Settings"
