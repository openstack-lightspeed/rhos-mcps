FROM registry.access.redhat.com/ubi9/python-312:latest

LABEL com.redhat.component="rhos-ls-mcps" \
      name="openstack-lightspeed/rhos-mcps" \
      summary="MCP server providing OpenStack on OpenShift tools for RHOS-Lightspeed" \
      io.k8s.name="rhos-mcps" \
      io.k8s.description="MCP Tools for RHOS-Lightspeed" \
      io.openshift.tags="openstack,lightspeed,mcp" \
      org.label-schema.vcs-url="https://github.com/openstack-lightspeed/rhos-mcps"

WORKDIR /app

# Install pdm for dependency management
RUN pip install --no-cache-dir pdm

# Copy dependency and build files first for better layer caching
COPY pyproject.toml pdm.lock README.md ./

# Copy the source code
COPY src/ src/

# Install the project and its dependencies using pdm (respects the lockfile)
RUN pdm install --prod --no-editable --frozen-lockfile

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8080

USER 1001

# Use the console_scripts entry point defined in pyproject.toml
ENTRYPOINT ["rhos-ls-mcps"]
