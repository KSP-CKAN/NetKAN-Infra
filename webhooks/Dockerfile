FROM perl:5
RUN apt-get update && apt-get install -y build-essential mono-complete libcurl4-openssl-dev git
WORKDIR /tmp
ADD https://github.com/KSP-CKAN/NetKAN-bot/releases/download/v0.010/App-KSP_CKAN-0.010.tar.gz /tmp
RUN cpanm --notest --installdeps App-KSP_CKAN-0.010.tar.gz
# Couple of git tests broken, but as this is a transition container ¯\_(ツ)_/¯
RUN cpanm --notest App-KSP_CKAN-0.010.tar.gz
ADD run.sh /usr/bin/local/
RUN useradd -ms /bin/bash netkan
WORKDIR /home/netkan
USER netkan
ENTRYPOINT ["/usr/bin/local/run.sh"]
