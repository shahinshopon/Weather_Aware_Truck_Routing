import React, { useEffect, useRef, useState } from "react";
import { MapPin, Loader2 } from "lucide-react";
import { fetchGeocodeSuggestions } from "../api/client";
import type { GeocodeLocation } from "../types/api";

interface LocationAutocompleteProps {
  label: string;
  value: GeocodeLocation;
  onChange: (loc: GeocodeLocation) => void;
  placeholder?: string;
  accentColorClass?: string;
}

export const LocationAutocomplete: React.FC<LocationAutocompleteProps> = ({
  label,
  value,
  onChange,
  placeholder = "Enter US city or highway hub...",
  accentColorClass = "text-sky-400",
}) => {
  const [inputText, setInputText] = useState(value.label);
  const [suggestions, setSuggestions] = useState<GeocodeLocation[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const wrapperRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setInputText(value.label);
  }, [value.label]);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (
        wrapperRef.current &&
        !wrapperRef.current.contains(e.target as Node)
      ) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  useEffect(() => {
    if (!isOpen || inputText.trim().length < 2) {
      setSuggestions([]);
      return;
    }

    const timer = setTimeout(async () => {
      setIsLoading(true);
      try {
        const results = await fetchGeocodeSuggestions(inputText);
        setSuggestions(results);
        setActiveIndex(results.length > 0 ? 0 : -1);
      } catch {
        setSuggestions([]);
      } finally {
        setIsLoading(false);
      }
    }, 200);

    return () => clearTimeout(timer);
  }, [inputText, isOpen]);

  const handleSelect = (loc: GeocodeLocation) => {
    setInputText(loc.label);
    onChange(loc);
    setIsOpen(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!isOpen || suggestions.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((prev) => (prev + 1) % suggestions.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((prev) =>
        prev <= 0 ? suggestions.length - 1 : prev - 1
      );
    } else if (e.key === "Enter" && activeIndex >= 0) {
      e.preventDefault();
      handleSelect(suggestions[activeIndex]);
    } else if (e.key === "Escape") {
      setIsOpen(false);
    }
  };

  return (
    <div ref={wrapperRef} className="relative flex-1">
      <label className="block text-[11px] font-semibold uppercase tracking-wider text-slate-400 mb-1">
        {label}
      </label>
      <div className="relative">
        <MapPin
          className={`w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 ${accentColorClass}`}
        />
        <input
          type="text"
          value={inputText}
          onFocus={() => setIsOpen(true)}
          onChange={(e) => {
            const txt = e.target.value;
            setInputText(txt);
            setIsOpen(true);
            onChange({ label: txt, lat: value.lat, lng: value.lng });
          }}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          aria-label={label}
          className="w-full bg-slate-900/90 border border-slate-700/80 rounded-lg pl-9 pr-8 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-sky-500/60 focus:border-sky-500 transition"
        />
        {isLoading && (
          <Loader2 className="w-4 h-4 text-slate-400 animate-spin absolute right-2.5 top-1/2 -translate-y-1/2" />
        )}
      </div>

      {isOpen && suggestions.length > 0 && (
        <ul
          role="listbox"
          className="absolute z-50 mt-1 w-full bg-slate-900 border border-slate-700 rounded-lg shadow-2xl max-h-56 overflow-auto divide-y divide-slate-800/70"
        >
          {suggestions.map((item, idx) => (
            <li
              key={`${item.label}-${item.lat}-${item.lng}`}
              role="option"
              aria-selected={idx === activeIndex}
              onMouseDown={(e) => {
                e.preventDefault();
                handleSelect(item);
              }}
              onMouseEnter={() => setActiveIndex(idx)}
              className={`px-3 py-2 text-xs cursor-pointer flex items-center justify-between ${
                idx === activeIndex
                  ? "bg-sky-500/20 text-sky-200"
                  : "text-slate-200 hover:bg-slate-800"
              }`}
            >
              <span className="font-medium truncate">{item.label}</span>
              <span className="text-[10px] text-slate-400 ml-2 shrink-0">
                {item.lat.toFixed(2)}°, {item.lng.toFixed(2)}°
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};
