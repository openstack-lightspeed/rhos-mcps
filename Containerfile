FROM registry.access.redhat.com/ubi9/python-312:latest AS builder

WORKDIR /app

# Install PDM in the builder only; not needed in the final image.
RUN pip install --no-cache-dir pdm

# Copy dependency manifests and README first (build backend needs README.md).
# Dependency layer is reused when only application code changes.
COPY pyproject.toml pdm.lock README.md ./
RUN pdm install --prod --no-editable --frozen-lockfile

# Copy application code and install the package into the venv.
COPY src/ src/
RUN pdm install --prod --no-editable --frozen-lockfile

# Final stage: smaller image without PDM or build tools.
FROM registry.access.redhat.com/ubi9/python-312:latest

LABEL com.redhat.component="rhos-ls-mcps" \
      name="openstack-lightspeed/rhos-mcps" \
      summary="MCP server providing OpenStack tools for RHOS-Lightspeed" \
      io.k8s.name="rhos-mcps" \
      io.k8s.description="MCP Tools for RHOS-Lightspeed" \
      io.openshift.tags="openstack,lightspeed,mcp" \
      org.label-schema.vcs-url="https://github.com/openstack-lightspeed/rhos-mcps"

WORKDIR /app

# Copy the virtualenv (includes the installed package with --no-editable) and README.
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/README.md /app/

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8080

USER 1001

ENTRYPOINT ["rhos-ls-mcps"]
