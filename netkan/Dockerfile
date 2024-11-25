FROM ubuntu:24.04 AS ubuntu_with_python

# Don't prompt for time zone
ENV DEBIAN_FRONTEND=noninteractive

# Install Git and Python
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    git libffi-dev openssh-client \
    python3 python-is-python3 ca-certificates curl && \
    apt-get clean && \
    curl -sSL https://bootstrap.pypa.io/get-pip.py -o get-pip.py && \
    rm /usr/lib/python3.12/EXTERNALLY-MANAGED && \
    python3 get-pip.py --no-input && rm get-pip.py
RUN groupmod -n 'netkan' 'ubuntu' && \
    usermod -l 'netkan' -d /home/netkan -m ubuntu

FROM ubuntu_with_python AS base
COPY . /netkan
WORKDIR /netkan
RUN chown -R netkan:netkan /netkan
USER netkan
RUN pip install --user . --no-warn-script-location

FROM ubuntu_with_python AS production
COPY --from=base /home/netkan/.local /home/netkan/.local
RUN chown -R netkan:netkan /home/netkan
WORKDIR /home/netkan
USER netkan
COPY .gitconfig .
ENV PATH="$PATH:/home/netkan/.local/bin"
ENV PYTHONPATH=/home/netkan/.local/lib/python3.10/site-packages
RUN /home/netkan/.local/bin/netkan --help
ENTRYPOINT ["/home/netkan/.local/bin/netkan"]
CMD ["--help"]

FROM production AS test
USER root
COPY . /netkan
RUN chown -R netkan:netkan /netkan
USER netkan
WORKDIR /netkan
RUN pip install --user .[test]
RUN /home/netkan/.local/bin/pytest -v

FROM production AS dev
USER root
ADD . /netkan
RUN chown -R netkan:netkan /netkan
COPY run_dev.sh /usr/local/bin/
USER netkan
RUN pip install --user /netkan/.[development]
ENTRYPOINT ["/usr/local/bin/run_dev.sh"]

FROM production
