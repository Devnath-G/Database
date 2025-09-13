#============================================================================
# Copyright (C) 2022 Intel Corporation
#
# SPDX-License-Identifier: MIT
#============================================================================
FROM eef-metro1.5/metro-sdk:1.5
ARG https_proxy
ARG http_proxy
ARG no_proxy

USER metro
ENV HOME=/home/metro
WORKDIR /home/metro

# Install required packages
RUN pip install \
    openvino==2025.3.0 \
    opencv-python \
    transformers \
    sentencepiece \
    optimum-intel \
    nncf \
    intel_extension_for_pytorch \
    torchvision \
    websocket-client \
    websockets

# Copy project files
COPY --chown=metro:metro entrypoint.sh .
RUN chmod 755 entrypoint.sh

RUN mkdir models store
COPY --chown=metro:metro models ./models

ENTRYPOINT ["/bin/bash"]
CMD ["./entrypoint.sh"]
