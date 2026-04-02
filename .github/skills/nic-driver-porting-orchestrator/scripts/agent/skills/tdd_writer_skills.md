# TDD Writer Agent Skills

Best Known Methods (BKMs) for Phase 2: writing failing CppUTest tests before any porting code.

## Domain Knowledge

### CppUTest Conventions

- Test groups correspond to source modules: `TEST_GROUP(RxRing)`, `TEST_GROUP(TxDescriptor)`
- Each test covers one behaviour: `TEST(RxRing, AllocateDescriptorsReturnsSuccess)`
- Use `CHECK_EQUAL`, `LONGS_EQUAL`, `POINTERS_EQUAL`, `CHECK_TRUE` macros
- Mock hardware register reads with `mock().expectOneCall("read_reg").withParameter("offset", 0x1234).andReturnValue(0)`

### Test Coverage Targets

Every ported module must have tests for:

| Category | Example |
| -------- | ------- |
| Descriptor ring alloc/free | `TEST(RxRing, AllocRingSuccess)` |
| Tx packet enqueue | `TEST(TxPath, EnqueueSinglePacket)` |
| Rx packet dequeue | `TEST(RxPath, DequeueReceiveBuffer)` |
| Register read/write | `TEST(HwAccess, ReadRegisterBAR0)` |
| Error paths | `TEST(RxRing, AllocRingOutOfMemory)` |
| Edge cases | `TEST(TxPath, ZeroLengthPacket)` |

### Test File Layout

```text
tests/
├── AllTests.cpp          # main() with RunAllTests()
├── test_rx_ring.cpp
├── test_tx_path.cpp
├── test_hw_access.cpp
├── mocks/
│   ├── mock_bus_dma.cpp
│   └── mock_register_io.cpp
└── Makefile
```

### Rules

- Tests must compile and **fail** before any porting code exists (red phase)
- Do not stub out the function under test — only mock its OS/HW dependencies
- Keep each test under 30 lines; prefer many small tests over few large ones
- Name tests `<Module>_<Behaviour>` for easy grep
