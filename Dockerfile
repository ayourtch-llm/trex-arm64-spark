# TRex ARM64 (aarch64) Docker build
# Targets: DGX Spark with ConnectX-7 (MLX5)
#
# Build:   docker build -t trex-arm64:latest .
# Run:     docker run --privileged --network host \
#            -v /dev/hugepages:/dev/hugepages \
#            -v /dev/infiniband:/dev/infiniband \
#            trex-arm64:latest
#
# The build uses system-installed ibverbs/mlx5 libraries since
# upstream TRex only bundles x86_64 versions.

FROM ubuntu:24.04 AS builder

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    cmake \
    pkg-config \
    python3 \
    python3-dev \
    python3-pip \
    python3-venv \
    pciutils \
    linux-headers-generic \
    libnuma-dev \
    libibverbs-dev \
    librdmacm-dev \
    libmnl-dev \
    libelf-dev \
    meson \
    ninja-build \
    curl \
    wget \
    zlib1g-dev \
    libssl-dev \
    libzmq3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy the patched source tree (with aarch64 fixes)
COPY . /src/trex-core

WORKDIR /src/trex-core

# Populate scripts/so/aarch64/ with system libstdc++ and libzmq
# This directory must exist before ./b build (waf post-build symlinks .so files here)
RUN mkdir -p scripts/so/aarch64 && \
    cp /usr/lib/aarch64-linux-gnu/libstdc++.so.6 scripts/so/aarch64/ && \
    cp /usr/lib/aarch64-linux-gnu/libzmq.so.5 scripts/so/aarch64/ 2>/dev/null || true

# Replace bundled ancient zmq 3.2 headers with system zmq 4.x for aarch64
RUN cp /usr/include/zmq.h external_libs/zmq/aarch64/include/zmq.h && \
    cp /usr/include/zmq_utils.h external_libs/zmq/aarch64/include/zmq_utils.h 2>/dev/null || true && \
    cp /usr/lib/aarch64-linux-gnu/libzmq.so external_libs/zmq/aarch64/libzmq.so 2>/dev/null || true

# Create ibverbs aarch64 directory with system libraries
RUN mkdir -p external_libs/ibverbs/aarch64/include && \
    cp -r /usr/include/infiniband external_libs/ibverbs/aarch64/include/ && \
    cp /usr/lib/aarch64-linux-gnu/libibverbs.so external_libs/ibverbs/aarch64/ && \
    if [ -f /usr/lib/aarch64-linux-gnu/libmlx5.so ]; then \
        cp /usr/lib/aarch64-linux-gnu/libmlx5.so external_libs/ibverbs/aarch64/; \
    elif [ -f /usr/lib/aarch64-linux-gnu/libmlx5-rdmav2.so ]; then \
        cp /usr/lib/aarch64-linux-gnu/libmlx5-rdmav2.so external_libs/ibverbs/aarch64/libmlx5.so; \
    fi

# Configure and build TRex
WORKDIR /src/trex-core/linux_dpdk
RUN ./b configure 2>&1 | tail -40
RUN ./b build 2>&1 | tail -20

# Create symlinks if waf post-build failed to (happens when so/ symlinks fail)
RUN if [ ! -e /src/trex-core/scripts/_t-rex-64 ]; then \
        if [ -f /src/trex-core/linux_dpdk/build_dpdk/linux_dpdk/_t-rex-64 ]; then \
            ln -sf ../linux_dpdk/build_dpdk/linux_dpdk/_t-rex-64 /src/trex-core/scripts/_t-rex-64; \
            ln -sf ../linux_dpdk/build_dpdk/linux_dpdk/_t-rex-64-o /src/trex-core/scripts/_t-rex-64-o 2>/dev/null; \
            echo "Created missing symlinks"; \
        else \
            echo "BUILD FAILED: _t-rex-64 binary not found"; \
            exit 1; \
        fi; \
    fi && \
    ls -la /src/trex-core/scripts/_t-rex-64

# Create missing .so symlinks in scripts/so/aarch64/ if waf didn't
RUN for so in /src/trex-core/linux_dpdk/build_dpdk/linux_dpdk/lib*.so; do \
        base=$(basename "$so"); \
        target="/src/trex-core/scripts/so/aarch64/$base"; \
        if [ ! -e "$target" ]; then \
            cp "$so" "$target" 2>/dev/null || true; \
        fi; \
    done

# ---- Runtime image ----
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    libnuma1 \
    libibverbs1 \
    ibverbs-providers \
    rdma-core \
    librdmacm1 \
    libmnl0 \
    libelf1t64 \
    libsodium23 \
    libzmq5 \
    pciutils \
    iproute2 \
    net-tools \
    ethtool \
    strace \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /src/trex-core /opt/trex

WORKDIR /opt/trex/scripts

# Make the binary executable
RUN chmod +x _t-rex-64 t-rex-64 2>/dev/null || true

# Populate pyzmq arm/64bit with system libzmq for TRex Python API
RUN mkdir -p external_libs/pyzmq-ctypes/zmq/arm/64bit && \
    cp /usr/lib/aarch64-linux-gnu/libzmq.so.5 external_libs/pyzmq-ctypes/zmq/arm/64bit/libzmq.so

ENTRYPOINT ["/bin/bash"]
