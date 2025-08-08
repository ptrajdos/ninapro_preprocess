ROOTDIR=$(realpath $(dir $(firstword $(MAKEFILE_LIST))))


SRCDIR=${ROOTDIR}/ninapro_preprocess
INSTALL_LOG_FILE=${ROOTDIR}/install.log
VENV_SUBDIR=${ROOTDIR}/venv


DATADIR=${ROOTDIR}/data
DB3_DIR=${DATADIR}/DB3
DB2_DIR=${DATADIR}/DB2


PYTHON=python
SYSPYTHON=python
PIP=pip
TAR := $(shell command -v gtar >/dev/null 2>&1 && echo gtar || echo tar)
CURL=curl
AXEL=axel

LOGDIR=${ROOTDIR}/testlogs
LOGFILE=${LOGDIR}/`date +'%y-%m-%d_%H-%M-%S'`.log

VENV_OPTIONS=

DB3_URL := https://ninapro.hevs.ch/files/db3_Preproc/
DB3_FNUMS := $(shell seq 1 11)
DB3_FILES := $(patsubst %,s%_0.zip,$(DB3_FNUMS))
DB3_TARGETS := $(addprefix $(DB3_DIR)/,$(DB3_FILES))
DB3_UNPACK_DIRS := $(patsubst %.zip,%,$(DB3_TARGETS))

#https://ninapro.hevs.ch/files/DB2_Preproc/DB2_s1.zip
DB2_URL := https://ninapro.hevs.ch/files/DB2_Preproc/
DB2_FNUMS := $(shell seq 1 40)
DB2_FILES := $(patsubst %,DB2_s%.zip,$(DB2_FNUMS))
DB2_TARGETS := $(addprefix $(DB2_DIR)/,$(DB2_FILES))
DB2_UNPACK_DIRS := $(patsubst %.zip,%,$(DB2_TARGETS))


ifeq ($(OS),Windows_NT)
	ACTIVATE:=. ${VENV_SUBDIR}/Scripts/activate
else
	ACTIVATE:=. ${VENV_SUBDIR}/bin/activate
endif

.PHONY: all clean test docs

all: extractor1

clean:
	rm -rf ${VENV_SUBDIR}

venv:
	${SYSPYTHON} -m venv --upgrade-deps ${VENV_OPTIONS} ${VENV_SUBDIR}
	${ACTIVATE}; ${PYTHON} -m ${PIP} install -e ${ROOTDIR} --prefer-binary --log ${INSTALL_LOG_FILE}

prepare_db3: $(DB3_TARGETS) $(DB3_UNPACK_DIRS)
	@echo "Preparing DB3"

prepare_db2: $(DB2_TARGETS) $(DB2_UNPACK_DIRS)
	@echo "Preparing DB2"
prepare_data: prepare_db3 prepare_db2
	@echo "Prepare data"

extractor_DB3_A: venv prepare_data
	@echo "Extractor1"
	${ACTIVATE}; extractor_DB3_A

$(DB3_DIR):
	mkdir -p ${DB3_DIR}



$(DB3_DIR)/%.zip: |$(DB3_DIR)
	@echo "Dowloading $@ ..."
	#$(CURL) -L -o $@ $(DB3_URL)$*.zip
	$(AXEL) -o $@ $(DB3_URL)$*.zip

$(DB3_DIR)/%: $(DB3_DIR)/%.zip
	@echo "Unzipping $< into $@"
	unzip -d $(DB3_DIR) -o -j $< 'DB3_s*/*.mat'

clean_db3:
	rm -rf ${DB3_DIR}

#DB2

$(DB2_DIR):
	mkdir -p ${DB2_DIR}

$(DB2_DIR)/%.zip: |$(DB2_DIR)
	@echo "Dowloading $@ ..."
	#$(CURL) -L -o $@ $(DB2_URL)$*.zip
	$(AXEL) -o $@ $(DB2_URL)$*.zip

$(DB2_DIR)/%: $(DB2_DIR)/%.zip
	@echo "Unzipping $< into $@"
	unzip -d $(DB2_DIR) -o -j $< 'DB2_s*/*.mat'

clean_db2:
	rm -rf ${DB2_DIR}
