FROM mambaorg/micromamba:latest@sha256:dc6e3fc34e7d8179ee2f1af3218b59bc17b2625d0ef5d31190de28ced840007f

LABEL org.opencontainers.image.source="https://github.com/sepal-contrib/sdg_15.3.1"

WORKDIR /usr/local/lib/sdg_15_3_1

USER root
# libjemalloc2: allocator for the runtime (see ENV block near the end).
RUN apt-get update && apt-get install -y \
    nano curl neovim supervisor netcat-openbsd net-tools git libjemalloc2 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /tmp/* \
    && rm -rf /var/tmp/*

COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Ownership so the editable install can write its build metadata into the tree.
COPY . /usr/local/lib/sdg_15_3_1
RUN chown -R $MAMBA_USER:$MAMBA_USER /usr/local/lib/sdg_15_3_1

USER $MAMBA_USER

# NOT built from sepal_environment.yml: that file pins `pysepal<4` for
# `component/`, which this image does not ship (.dockerignore drops it). The
# app extra's `pysepal>=4` is the whole point, so the two cannot share an env
# until spec 2/3 retires the legacy package.
#
# The openforis earthengine-api fork goes in FIRST. It reports 1.6.14, so the
# `earthengine-api==1.6.14` pin in pyproject.toml is already satisfied when the
# project installs and pip leaves it alone; install it after and PyPI's stock
# build -- which the goldens were not generated against -- wins the resolve.
RUN micromamba create -n sdg_15_3_1 python=3.12 pip -c conda-forge -y && \
    micromamba run -n sdg_15_3_1 pip install --no-cache-dir \
      "git+https://github.com/openforis/earthengine-api.git@v1.6.14#egg=earthengine-api&subdirectory=python" && \
    micromamba run -n sdg_15_3_1 pip install --no-cache-dir -e ".[app]" && \
    micromamba run -n sdg_15_3_1 python -c "import ee, sys; sys.exit(0 if ee.__version__ == '1.6.14' else 'ee-api is ' + ee.__version__)" && \
    micromamba clean --all --yes && \
    rm -rf ~/.cache/pip

# Run under jemalloc so freed per-session memory returns to the OS. glibc/pymalloc
# never release the arenas dented by per-session widget churn, so RSS ratchets to
# the peak working set and stays there until restart; jemalloc purges free pages
# on a decay timer, so memory follows users back down. Measured on se.plan and
# sepal_mgci, which run the same per-kernel Solara shape.
# NOTE: if the .so is missing, LD_PRELOAD is silently ignored and PYTHONMALLOC=malloc
# is worse than stock — after any image change verify jemalloc is actually loaded:
#   grep -c jemalloc /proc/<solara-python-pid>/maps   # >= 1
# Placed after the build layers so image builds don't run under the preload.
ENV LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libjemalloc.so.2 \
    PYTHONMALLOC=malloc \
    MALLOC_CONF=background_thread:true,dirty_decay_ms:1000,muzzy_decay_ms:1000

EXPOSE 8767

USER root
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
