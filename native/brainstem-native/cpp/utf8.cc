#include <cstddef>
#include <cstdint>

extern "C" int brainstem_has_nul_fallback(const std::uint8_t* data, std::size_t length) {
  for (std::size_t index = 0; index < length; ++index) {
    if (data[index] == 0) return 1;
  }
  return 0;
}

extern "C" int brainstem_utf8_validate(const std::uint8_t* data, std::size_t length) {
  std::size_t index = 0;
  while (index < length) {
    const std::uint8_t first = data[index++];
    if (first <= 0x7f) continue;
    if (first >= 0xc2 && first <= 0xdf) {
      if (index >= length || (data[index++] & 0xc0) != 0x80) return 0;
      continue;
    }
    if (first >= 0xe0 && first <= 0xef) {
      if (index + 1 >= length) return 0;
      const std::uint8_t second = data[index++];
      const std::uint8_t third = data[index++];
      if ((second & 0xc0) != 0x80 || (third & 0xc0) != 0x80) return 0;
      if (first == 0xe0 && second < 0xa0) return 0;
      if (first == 0xed && second > 0x9f) return 0;
      continue;
    }
    if (first >= 0xf0 && first <= 0xf4) {
      if (index + 2 >= length) return 0;
      const std::uint8_t second = data[index++];
      const std::uint8_t third = data[index++];
      const std::uint8_t fourth = data[index++];
      if ((second & 0xc0) != 0x80 || (third & 0xc0) != 0x80 || (fourth & 0xc0) != 0x80) return 0;
      if (first == 0xf0 && second < 0x90) return 0;
      if (first == 0xf4 && second > 0x8f) return 0;
      continue;
    }
    return 0;
  }
  return 1;
}
