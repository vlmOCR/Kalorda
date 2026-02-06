<template>
    <div :class="cx('root')" v-bind="ptmi('root')">
        <div ref="toolbarElement" :class="cx('toolbar')" v-bind="ptm('toolbar')">
            <slot name="toolbar">
                <span class="ql-formats" v-bind="ptm('formats')">
                    <select class="ql-header" defaultValue="0" v-bind="ptm('header')">
                        <option value="1" v-bind="ptm('option')">Heading</option>
                        <option value="2" v-bind="ptm('option')">Subheading</option>
                        <option value="0" v-bind="ptm('option')">Normal</option>
                    </select>
                    <select class="ql-font" v-bind="ptm('font')">
                        <option v-bind="ptm('option')"></option>
                        <option value="serif" v-bind="ptm('option')"></option>
                        <option value="monospace" v-bind="ptm('option')"></option>
                    </select>
                </span>
                <span class="ql-formats" v-bind="ptm('formats')">
                    <button class="ql-bold" type="button" v-bind="ptm('bold')"></button>
                    <button class="ql-italic" type="button" v-bind="ptm('italic')"></button>
                    <button class="ql-underline" type="button" v-bind="ptm('underline')"></button>
                </span>
                <span class="ql-formats" v-bind="ptm('formats')">
                    <select class="ql-color" v-bind="ptm('color')"></select>
                    <select class="ql-background" v-bind="ptm('background')"></select>
                </span>
                <span class="ql-formats" v-bind="ptm('formats')">
                    <button class="ql-list" value="ordered" type="button" v-bind="ptm('list')"></button>
                    <button class="ql-list" value="bullet" type="button" v-bind="ptm('list')"></button>
                    <select class="ql-align" v-bind="ptm('select')">
                        <option defaultValue v-bind="ptm('option')"></option>
                        <option value="center" v-bind="ptm('option')"></option>
                        <option value="right" v-bind="ptm('option')"></option>
                        <option value="justify" v-bind="ptm('option')"></option>
                    </select>
                </span>
                <span class="ql-formats" v-bind="ptm('formats')">
                    <button class="ql-link" type="button" v-bind="ptm('link')"></button>
                    <button class="ql-image" type="button" v-bind="ptm('image')"></button>
                    <button class="ql-code-block" type="button" v-bind="ptm('codeBlock')"></button>
                </span>
                <span class="ql-formats" v-bind="ptm('formats')">
                    <button class="ql-clean" type="button" v-bind="ptm('clean')"></button>
                </span>
            </slot>
        </div>
        <div ref="editorElement" :class="cx('content')" :style="editorStyle" v-bind="ptm('content')" spellcheck="false">
        </div>
    </div>
</template>

<script>
// 整合PrimeVue的Editor组件的两个文件为一个文件，微调以支持自定义handlers
import BaseEditableHolder from '@primevue/core/baseeditableholder';
import EditorStyle from 'primevue/editor/style';
import { isExist } from '@primeuix/utils/dom';
import { getLanguage } from '@/assets/lang/language';

const QuillJS = (function () {
    try {
        return window.Quill;
    } catch {
        return null;
    }
})();

export default {
    name: 'Editor',
    extends: {
        name: 'BaseEditor',
        extends: BaseEditableHolder,
        props: {
            placeholder: String,
            readonly: Boolean,
            formats: Array,
            editorStyle: null,
            modules: null,
            handlers: null // 对自定义Quill的工具栏handlers支持 edit by sanjer
        },
        style: EditorStyle,
        provide() {
            return {
                $pcEditor: this,
                $parentInstance: this
            };
        }
    },
    inheritAttrs: false,
    emits: ['text-change', 'selection-change', 'load'],
    quill: null,
    watch: {
        modelValue(newValue, oldValue) {
            if (newValue !== oldValue && this.quill && !this.quill.hasFocus()) {
                this.renderValue(newValue);
            }
        },
        readonly() {
            this.handleReadOnlyChange();
        }
    },
    mounted() {
        const configuration = {
            modules: {
                // toolbar: this.$refs.toolbarElement,
                // 对自定义Quill的工具栏handlers支持 edit by sanjer
                toolbar: {
                    container: this.$refs.toolbarElement,
                    handlers: this.handlers || {}
                },
                'table-better': {
                    language: getLanguage().code,
                    toolbarButtons: {
                        whiteList: [],
                        singleWhiteList: []
                    },
                    // menus: ['column', 'row', 'merge', 'table', 'cell', 'wrap', 'copy', 'delete'],
                    menus: ['column', 'row', 'merge', 'wrap', 'delete'],
                    toolbarTable: true
                },
                ...this.modules
            },
            readOnly: this.readonly,
            theme: 'snow',
            formats: this.formats,
            placeholder: this.placeholder
        };

        if (QuillJS) {
            // Loaded by script only
            this.quill = new QuillJS(this.$refs.editorElement, configuration);
            this.initQuill();
            this.handleLoad();
        } else {
            import('quill')
                .then((module) => {
                    if (module && isExist(this.$refs.editorElement)) {
                        if (module.default) {
                            // webpack
                            this.quill = new module.default(this.$refs.editorElement, configuration);
                        } else {
                            // parceljs
                            this.quill = new module(this.$refs.editorElement, configuration);
                        }

                        this.initQuill();
                    }
                })
                .then(() => {
                    this.handleLoad();
                });
        }
    },
    beforeUnmount() {
        this.quill = null;
    },
    methods: {
        renderValue(value) {
            if (this.quill) {
                this.quill.setText('');
                // this.quill.root.innerHTML = "";
                if (value) {
                    // Preserve full-width spaces (U+3000) across Quill clipboard normalization.
                    const placeholder = '\uE000'; // Private Use Area placeholder
                    const valueWithPlaceholder = value.replace(/\u3000/g, placeholder);
                    const delta = this.quill.clipboard.convert({ html: valueWithPlaceholder });
                    if (delta?.ops && Array.isArray(delta.ops)) {
                        delta.ops = delta.ops.map((op) => {
                            if (typeof op.insert === 'string') {
                                op.insert = op.insert.replace(new RegExp(placeholder, 'g'), '\u3000');
                            }
                            return op;
                        });
                    }
                    // const delta = this.quill.clipboard.convert({ html: value });
                    this.quill.updateContents(delta);
                }
            }
        },
        initQuill() {
            this.renderValue(this.d_value);

            this.quill.on('text-change', (delta, oldContents, source) => {
                if (source === 'user') {
                    let html = this.quill.getSemanticHTML();
                    let text = this.quill.getText().trim();

                    // edit by sanjer
                    // if (html === '<p><br></p>') {
                    //     html = '';
                    // }

                    // html = html.replace(/<p>[\s]*?<\/p>/g, '');
                    // html = html.replace(/<p><br[^<>]*?><\/p>/g, '');
                    // html = html.replace(/&nbsp;/g, ' ');

                    this.writeValue(html);
                    this.$emit('text-change', {
                        htmlValue: html,
                        textValue: text,
                        delta: delta,
                        source: source,
                        instance: this.quill
                    });
                }
            });

            this.quill.on('selection-change', (range, oldRange, source) => {
                let html = this.quill.getSemanticHTML();
                let text = this.quill.getText().trim();

                this.$emit('selection-change', {
                    htmlValue: html,
                    textValue: text,
                    range: range,
                    oldRange: oldRange,
                    source: source,
                    instance: this.quill
                });
            });
        },
        handleLoad() {
            if (this.quill && this.quill.getModule('toolbar')) {
                this.$emit('load', { instance: this.quill });
            }
        },
        handleReadOnlyChange() {
            if (this.quill) this.quill.enable(!this.readonly);
        }
    }
};
</script>
