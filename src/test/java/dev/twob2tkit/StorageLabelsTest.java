package dev.twob2tkit;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import dev.twob2tkit.storage.StorageLabels;

final class StorageLabelsTest {
	@Test
	void signLinesAreJoinedWithoutEmptyRows() {
		assertEquals("小麦 种子", StorageLabels.joinSignLines("小麦", "", "种子", "  "));
		assertEquals("", StorageLabels.joinSignLines("", " ", null));
	}

	@Test
	void dyeIdsHaveChineseLabels() {
		assertEquals("红", StorageLabels.colorLabel("red"));
		assertEquals("浅蓝", StorageLabels.colorLabel("light_blue"));
		assertEquals("铜", StorageLabels.colorLabel("copper"));
		assertEquals("", StorageLabels.colorLabel(""));
	}
}
