package dev.twob2tkit.structure;

import java.util.Locale;
import java.util.Objects;

/** Scope and arrival lifecycle, independent of screens and other active automation. */
public final class GuideSession {
	private String scope;
	private int arrivedTicks;
	public void start(String world) { scope=world; arrivedTicks=0; }
	public void stop() { scope=null; arrivedTicks=0; }
	public boolean matches(String world) { return scope!=null && Objects.equals(scope,world); }
	public boolean arrived(double horizontal,double vertical) {
		arrivedTicks=horizontal<=3 && Math.abs(vertical)<=3 ? arrivedTicks+1 : 0;
		return arrivedTicks>=10;
	}
	public static String distance(double blocks) {
		return blocks>=1000 ? String.format(Locale.ROOT,"%.1f km",blocks/1000) : Math.round(blocks)+" 格";
	}
}
