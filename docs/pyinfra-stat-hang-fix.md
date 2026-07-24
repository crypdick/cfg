# pyinfra stat Command Issue

## Automated Fix

`cfg host apply` automatically detects and fixes the stat issue. **No manual setup required.**

### What happens

- **First-time**: Configures GNU stat via update-alternatives (requires sudo)
- **After package updates**: Automatically switches back to GNU stat if reverted

### For other hosts

Just run `cfg host apply` - it handles everything automatically.

### Technical Details

See `cfg/core/system_checks.py` module docstring for:
- Root cause explanation
- Performance benchmarks
- Package details
- Implementation notes

### If not using cfg

Manual setup:
```bash
sudo update-alternatives --install /usr/bin/stat stat /usr/bin/gnustat 100
sudo update-alternatives --install /usr/bin/stat stat /usr/lib/cargo/bin/coreutils/stat 50
sudo update-alternatives --set stat /usr/bin/gnustat
```

After package updates:
```bash
sudo update-alternatives --set stat /usr/bin/gnustat
```
