# method-co-evolution

Method Co-Evolution

---

## Build and Run

### Create virtual environment

```bash
python -m venv .venv
```

### Install Dependencies

```bash
source .venv/bin/activate
pip install -e ./method-history-collector --upgrade
pip install -e ./co-evolution --upgrade
```

### Run
```bash
mhc scan-method \
    --cache_directory ".cache" \
    --repository_directory ".cache/repository" \
    --data_directory ".cache/data" \
    --jar_directory ".cache/jar" \
    --repository_name "checkstyle"
    
mhc history \
    --cache_directory ".cache" \
    --repository_directory ".cache/repository" \
    --data_directory ".cache/data" \
    --jar_directory ".cache/jar" \
    --tool_name "codeShovel" \
    --repository_name "checkstyle"
    
mhc call-graph \
    --cache_directory ".cache" \
    --repository_directory ".cache/repository" \
    --data_directory ".cache/data" \
    --jar_directory ".cache/jar" \
    --tool_name "methodParser" \
    --repository_name "checkstyle"
    
```