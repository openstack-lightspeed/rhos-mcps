# rhos-ls-mcps

pdm run rhos-ls-mcps

## Container Image

The container image is available at `quay.io/openstack-lightspeed/rhos-mcps`.

### Running the image
```bash
podman run -p 8080:8080 quay.io/openstack-lightspeed/rhos-mcps:latest
```

The MCP server will start on port 8080. Connect to it using the Streamable HTTP endpoints:
```
http://localhost:8080/openstack/
http://localhost:8080/openshift/
```

They are separated because they require different credentials

### Running with a custom configuration

Create a `config.yaml` based on the [sample configuration](config.yaml.sample), then mount it into the container:
```bash
podman run -p 8901:8901 \
  -v ./config.yaml.sample:/app/config.yaml:Z \
  quay.io/openstack-lightspeed/rhos-mcps:latest
```

Adjust the port mapping to match the `port` value in your config file. If authentication is enabled in your config, include the token:
```bash
curl -X POST http://127.0.0.1:8901/openstack/ \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Authorization: Bearer supersecret" \
  -d '{"jsonrpc":"2.0","id":"1","method":"tools/list"}'
```

Adjust the port mapping to match the `port` value in your config file.

### Running with hardcoded credentials

If we are using CRC and we have done a deployment we can just get the
credentials and certs for openshift and openstack inside the container by:

Getting the openstack credentials:

```bash
scripts/get-crc-creds.sh
```

Now running the container with:

```bash
podman run -p 8901:8901 \
  --user 1001 \
  -v ./config.yaml.sample:/app/config.yaml:Z \
  -v ./tls-ca-bundle.pem:/app/tls-ca-bundle.pem:Z \
  -v ./clouds.yaml:/app/clouds.yaml:Z \
  -v ./secure.yaml:/app/secure.yaml:Z \
  -v ./tls-ca-bundle.pem:/app/tls-ca-bundle.pem:Z \
  -v ~/.crc/machines/crc/kubeconfig:/opt/app-root/src/.kube/config:Z,U \
  quay.io/openstack-lightspeed/rhos-mcps:latest
```
